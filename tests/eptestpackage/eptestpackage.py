def main():
    print("eptestpackage:main")

def mainw():
    print("eptestpackage:mainw")

def do_refresh():
    import subprocess
    with subprocess.Popen(
        ["pymanager", "install", "-q", "--refresh"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="ascii",
        errors="replace",
    ) as p:
        out, _ = p.communicate(None)
        print(out)

    print("eptestpackage:do_refresh")
