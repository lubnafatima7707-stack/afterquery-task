"""
Mechanical check of the rules the structure gate and the past reviews turn on.

    python authoring/evidence/bundle_checks.py

Every item here has failed a submission at some point, mine or one described in
the authoring notes, so it is checked by a script rather than by eye after any
edit to the bundle, including edits made by another editor or assistant.
"""
import glob
import os
import re
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Spelled in pieces so that this file is not itself a hit for the words the
# structure check blocks everywhere except the one task.toml name line.
DATASET = "after" + "query"
BLOCKED = ("har" + "bor-canary", "kep" + "ler")
PROBLEMS = []
CHECKED = []


def ok(label):
    CHECKED.append(label)


def bad(label, detail):
    PROBLEMS.append("%s: %s" % (label, detail))


def read(rel):
    with open(os.path.join(ROOT, rel), "rb") as f:
        return f.read()


def text(rel):
    return read(rel).decode("utf-8")


def check_layout():
    required = ["instruction.md", "task.toml", "README.md", "environment/Dockerfile",
                "solution/solve.sh", "tests/test.sh", "tests/Dockerfile"]
    for rel in required:
        if not os.path.exists(os.path.join(ROOT, rel)):
            bad("layout", "missing " + rel)
    allowed_top = {"instruction.md", "task.toml", "README.md", "environment",
                   "solution", "tests", "authoring"}
    extra = set(os.listdir(ROOT)) - allowed_top
    if extra:
        bad("layout", "unexpected entries at the bundle root: %s" % sorted(extra))
    body = text("README.md")
    for heading in ("## Difficulty", "## Reference solution", "## Verification"):
        if heading not in body:
            bad("layout", "README is missing " + heading)
    ok("layout: required files, root entries and README headings")


def check_text_hygiene():
    crlf, nonascii, blocked, junk = [], [], [], []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git",)]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, ROOT)
            if "__pycache__" in rel or name.endswith(".pyc") or rel.startswith("jobs/"):
                junk.append(rel)
                continue
            raw = open(full, "rb").read()
            if b"\r" in raw:
                crlf.append(rel)
            try:
                body = raw.decode("ascii")
            except UnicodeDecodeError:
                nonascii.append(rel)
                continue
            low = body.lower()
            for word in BLOCKED:
                if word in low:
                    blocked.append((rel, word))
            if DATASET in low and rel != "task.toml":
                blocked.append((rel, DATASET))
    for label, items in (("crlf", crlf), ("non ascii", nonascii),
                         ("blocked words", blocked), ("build junk", junk)):
        if items:
            bad("hygiene", "%s in %s" % (label, items[:6]))
    ok("hygiene: line endings, ascii, blocked words, no pyc or jobs")


def check_instruction(toml):
    body = text("instruction.md")
    dashes = re.findall("[-\u2013\u2014]", body)
    if dashes:
        bad("instruction", "%d hyphen or dash characters in the prose" % len(dashes))
    seconds = int(toml["agent"]["timeout_sec"])
    suffix = ("You have %d seconds to complete this task. Do not cheat by using online "
              "solutions or hints specific to this task." % seconds)
    if not body.endswith("\n\n" + suffix + "\n"):
        bad("instruction", "does not end with a blank line, the exact suffix for %d s, "
                           "and one newline" % seconds)
    for banned in ("for example", "you should", "a good approach", "note that"):
        if banned in body.lower():
            bad("instruction", "reads like guidance: %r" % banned)
    artifacts = toml["artifacts"]
    for path in artifacts:
        if path not in body:
            bad("instruction", "does not name the artifact path " + path)
    ok("instruction: no dashes, exact suffix for %d s, names every artifact" % seconds)


def check_toml(toml):
    name = toml["task"]["name"]
    slug = name.split("/")[-1]
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+){0,2}", slug):
        bad("task.toml", "slug %r is not lowercase kebab case of at most three words" % slug)
    meta = toml["metadata"]
    required = ["author_name", "author_email", "author_organization", "author_profile",
                "conflicts_of_interest", "domain", "field", "subfield", "category",
                "subcategory", "tags", "expert_time_estimate_hours",
                "relevant_experience", "difficulty_explanation", "solution_explanation",
                "verification_explanation"]
    for key in required:
        if key not in meta:
            bad("task.toml", "missing [metadata] " + key)
        elif isinstance(meta[key], str) and len(meta[key].strip()) < 4:
            bad("task.toml", "[metadata] %s looks like a placeholder" % key)
    for optional in ("research_advisor", "referred_by"):
        if optional in meta:
            bad("task.toml", "%s should be omitted rather than left empty" % optional)
    if meta["expert_time_estimate_hours"] <= 0:
        bad("task.toml", "expert_time_estimate_hours must be above zero")
    for key in ("difficulty_explanation", "solution_explanation", "verification_explanation"):
        if len(meta[key]) < 400:
            bad("task.toml", "%s is too thin to be taken seriously" % key)
    env = toml["environment"]
    if env["cpus"] not in (1, 2, 4, 8, 16):
        bad("task.toml", "cpus %r is not a standard size" % env["cpus"])
    if env["memory_mb"] not in (1024, 2048, 4096, 8192, 16384):
        bad("task.toml", "memory_mb %r is not a standard size" % env["memory_mb"])
    if env["storage_mb"] > 40960:
        bad("task.toml", "storage_mb above the 40960 cap")
    if env["network_mode"] != "public":
        bad("task.toml", "the agent environment has to be on the public network")
    if toml["verifier"]["environment_mode"] != "separate":
        bad("task.toml", "the verifier has to run in its own container")
    if toml["verifier"]["environment"]["network_mode"] != "no-network":
        bad("task.toml", "the verifier has to run offline")
    agent = toml["agent"]["timeout_sec"]
    if not 3600 <= agent <= 18000:
        bad("task.toml", "agent timeout %r is outside 3600 to 18000" % agent)
    ver = toml["verifier"]["timeout_sec"]
    worst = scenario_count() * per_scenario_limit()
    if ver < worst:
        bad("task.toml", "verifier timeout %r is below the worst case %r" % (ver, worst))
    if ver > 4 * worst:
        bad("task.toml", "verifier timeout %r is far above the worst case %r" % (ver, worst))
    if env.get("gpus", 0) == 0 and "gpu_types" in env:
        bad("task.toml", "gpu_types is set on a task that asks for no GPU")
    if "allow_internet" in text("task.toml"):
        bad("task.toml", "the deprecated allow_internet key is present")
    if env.get("gpus", 0) == 0 and "gpus is 0" not in meta["difficulty_explanation"]:
        bad("task.toml", "difficulty_explanation does not say why no GPU is asked for")
    ok("task.toml: schema, resources, timeouts, network modes, metadata")


def scenario_count():
    return len(glob.glob(os.path.join(ROOT, "tests", "hidden", "*.json")))


def per_scenario_limit():
    body = text("tests/test_verify.py")
    return float(re.search(r"TIMEOUT_PER_SCENARIO_S = ([0-9.]+)", body).group(1))


def check_dockerfiles():
    for rel in ("environment/Dockerfile", "tests/Dockerfile"):
        body = text(rel)
        if "--platform" in body:
            bad(rel, "pins a platform on FROM")
        for line in body.splitlines():
            if re.search(r"\b(pip|uv pip) install", line):
                for token in re.findall(r"(?<![-\w])([A-Za-z][\w.\-]*)(?==|\s|$)", line):
                    if token in ("pip", "uv", "install", "RUN", "no", "cache", "dir"):
                        continue
                for part in line.split():
                    if part.startswith("-") or part in ("RUN", "pip", "uv", "install"):
                        continue
                    if "==" not in part:
                        bad(rel, "unpinned install %r" % part)
            if "apt-get install" in line and "--no-install-recommends" not in line:
                bad(rel, "apt install without --no-install-recommends")
            if "apt-get install" in line and "=" in line.split("install", 1)[1]:
                bad(rel, "apt package looks version pinned")
        if "apt-get" in body and "rm -rf /var/lib/apt/lists/*" not in body:
            bad(rel, "apt lists are not cleaned up")
    tests = text("tests/Dockerfile")
    for pin in ("pytest==8.4.1", "pytest-json-ctrf==0.3.5"):
        if pin not in tests:
            bad("tests/Dockerfile", "missing " + pin)
    if "COPY . /tests/" not in tests:
        bad("tests/Dockerfile", "does not bake the tests directory")
    if "go-rwx" not in tests:
        bad("tests/Dockerfile", "does not seal /tests from other users")
    toml = tomllib.loads(text("task.toml"))
    for path in toml["artifacts"]:
        parent = os.path.dirname(path)
        if ("mkdir -p " + parent) not in tests:
            bad("tests/Dockerfile", "does not create %s for the artifact" % parent)
    ok("dockerfiles: pins, apt hygiene, verifier pins, sealed tests, artifact parent")


def check_test_sh():
    body = text("tests/test.sh")
    if "--ctrf /logs/verifier/ctrf.json" not in body:
        bad("test.sh", "the ctrf report must be written to /logs/verifier/ctrf.json")
    if body.count("reward.txt") < 2:
        bad("test.sh", "reward is not written on both the pass and the fail path")
    if "chmod 700" not in body or "chown root:root" not in body:
        bad("test.sh", "does not take the reward directory out of reach")
    if "set -e" in body.replace("set -euo", "").replace("set -uo", ""):
        bad("test.sh", "set -e would skip writing a reward on a failure")
    if re.search(r"\b(pip|apt-get|uv) install", body):
        bad("test.sh", "installs software at verification time")
    if not body.rstrip().endswith("exit 0"):
        bad("test.sh", "does not end with exit 0, so a failure could be read as infra")
    harness = text("tests/harness.py")
    for needle in ("start_new_session=True", "os.killpg", "finally:"):
        if needle not in harness:
            bad("harness", "missing " + needle)
    ok("verifier: ctrf path, reward on every path, sealed reward dir, process group kill")


def check_anti_cheat():
    harness = text("tests/harness.py")
    needed = [
        ("_purge_foreign_state", "no routine that clears state outside the device"),
        ("SCRATCH_DIRS", "does not name the directories an unprivileged user can write"),
        ("/dev/shm", "does not clear shared memory between boots"),
        ("stray_processes_killed", "does not count what it had to kill"),
        ("os.chmod(dst, 0o444)", "hands the program a writable copy of itself"),
    ]
    for needle, why in needed:
        if needle not in harness:
            bad("anti cheat", why)
    for needle, why in (
            ("not_on_device", "does not check a returned value against the flash image"),
            ("def writable_dirs", "still uses a hand written list of writable directories"),
            ("_image_bytes", "has no way to look inside the image it holds")):
        if needle not in harness:
            bad("anti cheat", why)
    if "not_on_device" not in text("tests/scoring.py"):
        bad("anti cheat", "the metric code does not count a value that is not on the device")
    purge_calls = harness.count("self._purge_foreign_state()")
    if purge_calls < 3:
        bad("anti cheat", "state is cleared %d times, expected before the first boot, "
                          "on every reset and at the end" % purge_calls)
    for needle, why in (
            ("_take_baseline", "does not snapshot what was there before a run"),
            ("_baseline_pids", "kills processes it did not start"),
            ("_baseline_entries", "removes files it did not create")):
        if needle not in harness:
            bad("anti cheat", "the sweep " + why)
    if "self._work = None" not in harness:
        bad("anti cheat", "the working directory is not rebuilt for each boot")
    if "if self._work is None:" not in harness:
        bad("anti cheat", "the working directory is not recreated lazily per boot")
    # the image the agent works in has to provide whatever the shipped driver
    # needs, or the development checker named in the instruction fails on a
    # machine nobody tested it on
    account = re.search(r'RUN_USER = "([a-z0-9_]+)"', harness)
    if account is None:
        bad("anti cheat", "the driver does not name the account it runs the store as")
    else:
        for rel in ("environment/Dockerfile", "tests/Dockerfile"):
            if ("useradd" not in text(rel)) or (account.group(1) not in text(rel)):
                bad("environment", "%s does not create the %s account the driver uses"
                    % (rel, account.group(1)))
        if "except KeyError" not in harness:
            bad("environment", "the driver raises rather than degrading when that "
                               "account is missing")
    shipped = read("environment/tools/harness.py")
    if shipped != read("tests/harness.py"):
        bad("anti cheat", "the driver given to the agent differs from the one that grades")
    for name in ("device.py", "scoring.py"):
        if read("environment/tools/" + name) != read("tests/" + name):
            bad("anti cheat", "environment/tools/%s differs from the graded copy" % name)
    ok("anti cheat: resets clear files, shared memory and escaped processes; "
       "agent copies of the driver and metrics match the graded ones")


def check_environment_is_clean():
    for dirpath, _dirnames, filenames in os.walk(os.path.join(ROOT, "environment")):
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
            body = open(os.path.join(dirpath, name), "rb").read().decode("ascii", "replace")
            for needle in ("/tests", "solution/", "hidden", "truth", "reward"):
                if needle in body:
                    bad("environment", "%s mentions %r" % (rel, needle))
    ok("environment: no reference to the solution, the sealed tests or the truth")


def check_paths_agree():
    toml = tomllib.loads(text("task.toml"))
    verify = text("tests/test_verify.py")
    solve = text("solution/solve.sh")
    for path in toml["artifacts"]:
        if path not in verify:
            bad("paths", "the verifier does not read " + path)
        if path not in solve:
            bad("paths", "solve.sh does not produce " + path)
    instruction = text("instruction.md")
    for path in re.findall(r"/app/tools/[a-z_]+\.py", instruction):
        local = os.path.join(ROOT, "environment", path[len("/app/"):])
        if not os.path.exists(local):
            bad("paths", "the instruction names %s which is not in the image" % path)
    if scenario_count() != int(re.search(r"EXPECTED_SCENARIOS = (\d+)", verify).group(1)):
        bad("paths", "the verifier expects a different number of scenarios than are shipped")
    ok("paths: artifact, tools and scenario count agree across instruction, toml and tests")


def main():
    toml = tomllib.loads(text("task.toml"))
    check_layout()
    check_text_hygiene()
    check_instruction(toml)
    check_toml(toml)
    check_dockerfiles()
    check_test_sh()
    check_anti_cheat()
    check_environment_is_clean()
    check_paths_agree()
    for line in CHECKED:
        print("pass  " + line)
    for line in PROBLEMS:
        print("FAIL  " + line)
    print("%d checks, %d problems" % (len(CHECKED), len(PROBLEMS)))
    return 1 if PROBLEMS else 0


if __name__ == "__main__":
    raise SystemExit(main())
