import contextlib
import json
import re
import sys

from pathlib import Path

REPO = Path(__file__).absolute().parent.parent
sys.path.append(str(REPO / "src"))

from manage.urlutils import IndexDownloader
from manage.tagutils import CompanyTag, tag_or_range
from manage.verutils import Version


def usage():
    print("Usage: repartition-index.py [-i options <FILENAME> ...] [options <OUTPUT> ...]")
    print()
    print("  --windows-default  Implies default output files and configurations.")
    print()
    print("  -i <FILENAME>      One or more files or URLs to read existing entries from.")
    print("  -i -n/--no-recurse Do not follow 'next' info")
    print("If no files are provided, uses the current online index")
    print()
    print("  <OUTPUT>           Filename to write entries into")
    print("  -d/--allow-dup     Include entries written in previous outputs")
    print("  --only-dup         Only include entries written in previous outputs")
    print("  --pre              Include entries marked as prereleases")
    print("  -t/--tag TAG       Include only the specified tags (comma-separated)")
    print("  -r/--range RANGE   Include only the specified range (comma-separated)")
    print("  --latest-micro     Include only the latest x.y.z version")
    print("  --report           Write plain-text summary report")
    print()
    print("An output of 'nul' is permitted to drop entries.")
    print("Providing the same inputs and outputs is permitted, as all inputs are read")
    print("before any outputs are written.")
    sys.exit(1)


class ReadFile:
    def __init__(self):
        self.source = None
        self.recurse = True

    def add_arg(self, arg):
        if arg[:1] != "-":
            self.source = arg
            return True
        if arg in ("-n", "--no-recurse"):
            self.recurse = False
            return False
        raise ValueError("Unknown argument: " + arg)

    def execute(self, versions, context):
        for _, data in IndexDownloader(self.source, lambda *a: a):
            versions.extend(data["versions"])
            if not self.recurse:
                break


class SortVersions:
    def __init__(self):
        pass

    def add_arg(self, arg):
        raise ValueError("Unknown argument: " + arg)

    def _number_sortkey(self, k):
        bits = []
        for n in re.split(r"(\d+)", k):
            try:
                bits.append(f"{int(n):020}")
            except ValueError:
                bits.append(n)
        return tuple(bits)

    def _sort_key(self, v):
        from manage.tagutils import _CompanyKey, _DescendingVersion
        return (
            _DescendingVersion(v["sort-version"]),
            _CompanyKey(v["company"]),
            self._number_sortkey(v["id"]),
        )

    def execute(self, versions, context):
        versions.sort(key=self._sort_key)
        print("Processing {} entries".format(len(versions)))


class SplitToFile:
    def __init__(self):
        self.target = None
        self.allow_dup = False
        self.only_dup = False
        self.pre = False
        self.tag_or_range = []
        self._expect_tag_or_range = False
        self.latest_micro = False
        self.report = False

    def add_arg(self, arg):
        if arg[:1] != "-":
            if self._expect_tag_or_range:
                self.tag_or_range.append(tag_or_range(arg))
                self._expect_tag_or_range = False
                return False
            self.target = arg
            return True
        if arg in ("-d", "--allow-dup"):
            self.allow_dup = True
            return False
        if arg == "--only-dup":
            self.allow_dup = True
            self.only_dup = True
            return False
        if arg == "--pre":
            self.pre = True
            return False
        if arg in ("-t", "--tag", "-r", "--range"):
            self._expect_tag_or_range = True
            return False
        if arg == "--latest-micro":
            self.latest_micro = True
            return False
        if arg == "--report":
            self.report = True
            return False
        raise ValueError("Unknown argument: " + arg)

    def execute(self, versions, context):
        if self.report:
            if self.target != "nul":
                context.setdefault("reports", []).append(self.target)
            return
        written = context.setdefault("written", set())
        written_now = set()
        outputs = context.setdefault("outputs", {})
        if self.target != "nul":
            try:
                output = outputs[self.target]
            except KeyError:
                context.setdefault("output_order", []).append(self.target)
                output = outputs.setdefault(self.target, [])
        else:
            # Write to a list that'll be forgotten
            output = []

        latest_micro_skip = set()

        for i in versions:
            k = i["id"].casefold(), i["sort-version"].casefold()
            v = Version(i["sort-version"])
            if self.only_dup and k not in written_now:
                written_now.add(k)
                continue
            if not self.allow_dup and k in written:
                continue
            if not self.pre and v.is_prerelease:
                continue
            if self.tag_or_range and not any(
                r.satisfied_by(CompanyTag(i["company"], t))
                for r in self.tag_or_range
                for t in i["install-for"]
            ):
                continue
            if self.latest_micro:
                k2 = i["id"].casefold(), v.to_python_style(2, with_dev=False)
                if k2 in latest_micro_skip:
                    continue
                latest_micro_skip.add(k2)
            written.add(k)
            output.append(i)


class WriteFiles:
    def __init__(self):
        self.indent = None

    def add_arg(self, arg):
        if arg == "-w-indent":
            self.indent = 4
            return False
        if arg == "-w-indent1":
            self.indent = 1
            return False
        raise ValueError("Unknown argument: " + arg)

    @contextlib.contextmanager
    def open(self, file):
        file = Path(file)
        if file.match("nul"):
            import io
            yield io.StringIO()
        elif file.match("stdout"):
            yield sys.stdout
        else:
            with open(file, "w", encoding="utf-8") as f:
                yield f

    def st_size(self, file):
        file = Path(file)
        if file.match("nul"):
            return "no data written"
        if file.match("stdout"):
            return "n/a"
        return f"{Path(file).stat().st_size} bytes"

    def execute(self, versions, context):
        outputs = context.get("outputs") or {}
        output_order = context.get("output_order", [])
        report_data = {}
        for target, next_target in zip(output_order, [*output_order[1:], None]):
            data = {
                "versions": outputs[target]
            }
            if next_target:
                data["next"] = next_target
            for i in outputs[target]:
                report_data.setdefault(target, {}).setdefault(i["sort-version"].casefold(), []).append(i)
            with self.open(target) as f:
                json.dump(data, f, indent=self.indent)
            print("Wrote {} ({} entries, {} bytes)".format(
                target, len(data["versions"]), self.st_size(target)
            ))

        reports = context.get("reports", [])
        for target in reports:
            with self.open(target) as f:
                for output_target in output_order:
                    print("Written to", output_target, file=f)
                    data = report_data[output_target]
                    for key in data:
                        ids = ", ".join(i["id"] for i in data[key])
                        print("{}: {}".format(key, ids), file=f)
                    print(file=f)
            print("Wrote {} ({} bytes)".format(
                target, self.st_size(target)
            ))


def parse_cli(args):
    plan_read = []
    plan_split = []
    sort = SortVersions()
    action = None
    write = WriteFiles()
    for a in args:
        if a == "--windows-default":
            print("Using equivalent of: --pre --latest-micro -r >=3.11.0 index-windows.json")
            print("                     --pre -r >=3.11.0 index-windows-recent.json")
            print("                     index-windows-legacy.json")
            print("                     --report index-windows.txt")
            plan_split = [SplitToFile(), SplitToFile(), SplitToFile(), SplitToFile()]
            plan_split[0].target = "index-windows.json"
            plan_split[1].target = "index-windows-recent.json"
            plan_split[2].target = "index-windows-legacy.json"
            plan_split[3].target = "stdout"
            plan_split[3].report = True
            plan_split[0].pre = plan_split[1].pre = plan_split[2].pre = True
            plan_split[0].latest_micro = True
            plan_split[0].tag_or_range = [tag_or_range(">=3.11"), tag_or_range(">=3.13t")]
            plan_split[1].tag_or_range = [tag_or_range(">=3.11"), tag_or_range(">=3.13t")]
        elif a == "-i":
            action = ReadFile()
            plan_read.append(action)
        elif a.startswith("-s-"):
            sort.add_arg(a)
        elif a.startswith("-w-"):
            write.add_arg(a)
        else:
            try:
                if action is None:
                    action = SplitToFile()
                    plan_split.append(action)
                if action.add_arg(a):
                    action = None
                continue
            except ValueError as ex:
                print(ex)
            usage()
    if not plan_read:
        action = ReadFile()
        action.source = "https://www.python.org/ftp/python/index-windows.json"
        plan_read.append(action)
    if not plan_split:
        print("No outputs specified")
        print(args)
        usage()
    return [*plan_read, sort, *plan_split, write]


if __name__ == "__main__":
    plan = parse_cli(sys.argv[1:])
    VERSIONS = []
    CONTEXT = {}
    for p in plan:
        p.execute(VERSIONS, CONTEXT)
