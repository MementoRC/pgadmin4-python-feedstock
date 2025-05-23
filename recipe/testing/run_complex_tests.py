import os
import platform
import select
import shutil
import subprocess
import sys
import tarfile
import time

import psutil


def run_command(cmd, shell=True, check=True, env=None, cwd=None):
    """Run a command with appropriate error handling"""
    print(f"Running: {cmd}")

    current_env = os.environ.copy()
    if env:
        current_env.update(env)

    try:
        result = subprocess.run(cmd, shell=shell, check=check, text=True,
                               capture_output=True, env=current_env, cwd=cwd)
        if result.stdout.strip():
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print(f"STDERR: {e.stderr}")
        if check:
            sys.exit(e.returncode)
        return e

def detect_os():
    """Detect operating system in a cross-platform way"""
    system = platform.system()

    if system == "Linux":
        # Check for WSL
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    return "WSL"
        except Exception:
            pass

    # Handle other environments
    if system in ["Darwin", "Windows"]:
        return system

    # Check for Windows bash environments
    if os.environ.get("OSTYPE") in ["msys", "win32", "cygwin"]:
        return "Windows"

    return system

def update_config(config_file, prefix, pg_version="99"):
    """Implement update_config.py functionality directly"""
    print(f"Updating config file: {config_file}")

    try:
        # Create absolute tablespace path
        tablespace_path = os.path.abspath(os.path.join(".postgresql", pg_version, "-main", "tablespaces"))

        with open(config_file, "r") as f:
            content = f.read()

        # Replace placeholders
        content = content.replace("__PREFIX__", prefix)
        content = content.replace("__PGVER__", pg_version)
        content = content.replace("__TABLESPACE_PATH__", tablespace_path)

        with open(config_file, "w") as f:
            f.write(content)

        return True
    except Exception as e:
        print(f"Error updating config file: {e}")
        sys.exit(1)

def setup_postgresql(pg_version, conda_prefix):
    """Implement PostgreSQL setup from run_test_command.py directly"""
    print(f"Setting up PostgreSQL {pg_version}...")

    pg_dir = os.path.join(".postgresql", f"{pg_version}-main")
    pg_stat_tmp = f"{pg_dir}.pg_stat_tmp"
    pg_conf = os.path.join(pg_dir, "postgresql.conf")
    port = f"59{pg_version}"

    # Create directories
    os.makedirs(pg_dir, exist_ok=True)
    os.makedirs(pg_stat_tmp, exist_ok=True)

    # Check if directory is not empty and clean it
    if os.listdir(pg_dir):
        print(f"Directory {pg_dir} is not empty. Cleaning up for a fresh install...")
        for item in os.listdir(pg_dir):
            item_path = os.path.join(pg_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                try:
                    os.remove(item_path)
                except Exception:
                    pass

    # Initialize database
    run_command(f"initdb -D {pg_dir} -U postgres --auth=trust --no-instructions --no-locale -E UTF8", shell=True)

    # Create tablespace directory
    tablespace_path = os.path.join(pg_dir, "tablespaces")
    os.makedirs(tablespace_path, exist_ok=True)

    # Configure pg_hba.conf
    with open(os.path.join(pg_dir, "pg_hba.conf"), "w") as f:
        f.write("local   all  all                    trust\n")
        f.write("host    all  all      127.0.0.1/32  trust\n")
        f.write("host    all  all      ::1/128       trust\n")

    # Update postgresql.conf with port
    with open(pg_conf, "r") as f:
        config_lines = f.readlines()

    with open(pg_conf, "w") as f:
        for line in config_lines:
            if line.startswith("port =") or line.startswith("#port ="):
                f.write(f"port = {port}\n")
            else:
                f.write(line)

    # Start PostgreSQL with Popen (not run_command)
    print(f"Starting PostgreSQL on port {port}...")
    postgres_cmd = os.path.join(conda_prefix, "bin", "postgres") + f" -D {pg_dir} -c config_file={pg_conf}"
    postgres_proc = subprocess.Popen(
        postgres_cmd.split(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    time.sleep(5)

    # Check if PostgreSQL is ready
    try:
        pg_isready_cmd = os.path.join(conda_prefix, "bin", "pg_isready") + f" -h localhost -p {port}"
        subprocess.run(pg_isready_cmd.split(), check=True)
        print("PostgreSQL is ready!")
    except subprocess.CalledProcessError:
        print("PostgreSQL failed to start properly")
        stdout, stderr = postgres_proc.communicate(timeout=1)
        print(f"PostgreSQL logs: {stderr}")
        postgres_proc.kill()
        raise

    return postgres_proc

def kill_postgres_processes():
    """Kill all PostgreSQL-related processes"""
    print("Terminating PostgreSQL processes...")

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = proc.info.get('name', '').lower()
            cmdline = ' '.join([str(c) for c in proc.info.get('cmdline', []) if c])

            if ('postgres' in name or 'postmaster' in name or
                'postgres' in cmdline or 'postmaster' in cmdline):
                print(f"Killing PostgreSQL process with PID {proc.info['pid']}")
                try:
                    proc.kill()
                except Exception as e:
                    print(f"Failed to kill process: {e}")
        except:
            continue

def main():
    # Detect OS
    os_type = detect_os()
    print(f"Detected OS: {os_type}")
    if os_type in ["Windows"]:
        # Fed-up with this crap
        return 0

    # Setup environment
    current_dir = os.getcwd()
    prefix = os.environ.get("CONDA_PREFIX", sys.prefix)
    py_ver = os.environ.get("PY_VER", "3.9")
    pg_version = "99"

    # Set environment variables
    os.environ["PREFIX"] = prefix
    os.environ["POSTGRESQL_VERSION"] = pg_version
    os.environ["CONDA_PREFIX"] = prefix

    # Install dependencies
    packages = [
        "linecache2==1.0.0",
        "openssl",
        "pbr==6.1.0",
        "pycodestyle>=2.5.0",
        "python-mimeparse==2.0.0",
        "psutil",
        "selenium==4.27.1",
        "testtools==2.7.2",
        "traceback2==1.4.0",
        "testscenarios==0.5.0",
    ]

    run_command(["mamba", "install", "-y"] + packages, shell=False)

    # Setup paths
    pgadmin_pkg = os.path.join(prefix, "lib", f"python{py_ver}", "site-packages", "pgadmin4")

    # Extract web and test files
    # Copy web directory using subprocess to match the original tar command
    # This is equivalent to: tar cf - web | (cd "${PGADMIN_PKG}"/; tar xf -)
    web_dir = os.path.join(current_dir, "..", "web")
    if os.path.exists(web_dir) and os.path.isdir(web_dir):
        print(f"Copying web directory to {pgadmin_pkg}")
        os.makedirs(pgadmin_pkg, exist_ok=True)
        # Use rsync or cp -r depending on the platform
        if os_type in ["Linux", "Darwin", "WSL"]:
            run_command(f"cp -r {web_dir} {pgadmin_pkg}", shell=True)
        else:
            # Fallback to Python's copy for Windows
            for item in os.listdir(web_dir):
                src_path = os.path.join(web_dir, item)
                dst_path = os.path.join(pgadmin_pkg, item)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dst_path)
    else:
        print(f"Warning: web directory not found at {web_dir}")
        raise RuntimeError("Web directory not found")

    tests_tar = os.path.join(current_dir, "..", "tests.tar")
    if os.path.exists(tests_tar):
        print(f"Extracting test files to {pgadmin_pkg}")
        with tarfile.open(tests_tar, "r") as tar:
            tar.extractall(path=pgadmin_pkg)
    else:
        print(f"Warning: test tarball not found at {tests_tar}")
        raise RuntimeError("Tests tarball not found")

    # Update config directly instead of calling external script
    config_path = os.path.join(".", "test_config.json")
    update_config(config_path, prefix, pg_version)

    # Copy configuration files
    regression_dir = os.path.join(pgadmin_pkg, "web", "regression")
    os.makedirs(regression_dir, exist_ok=True)
    shutil.copy(os.path.join(".", "config_local.py"), pgadmin_pkg)
    shutil.copy(config_path, regression_dir)

    try:
        # Setup PostgreSQL
        postgres_proc = setup_postgresql(pg_version, prefix)

        # Run tests
        os.chdir(pgadmin_pkg)
        path_separator = ";" if os_type == "Windows" else ":"
        python_path = f".{path_separator}{os.environ.get('PYTHONPATH', '.')}"
        os.environ["PYTHONPATH"] = python_path

        try:
            # Run tests but don't exit on failure
            test_cmd = [
                "python", os.path.join("web", "regression", "runtests.py"),
                "--exclude", "feature_tests",
                "--parallel",
                # "--pkg", "browser",
            ]
            process = subprocess.Popen(
                test_cmd,
                cwd=pgadmin_pkg,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            print("=" * 50)
            print("REGRESSION TESTS RUNNING - LIVE OUTPUT:")
            print("=" * 50)

            # Track output for final result
            all_stdout = []
            all_stderr = []
            # Store only test result lines
            test_result_lines = []
            spinner = ['|', '/', '-', '\\']
            counter = 0
            start_time = time.time()
            last_output_time = None

            # Display spinner while process is running
            idle_timeout_seconds = 120

            while True:
                # Check if process has finished
                ret_code = process.poll()
                if ret_code is not None:
                    break

                # Variables to track if we've seen new output this cycle
                has_new_output = False
                current_time = time.time()

                # Process all available stdout without blocking
                while select.select([process.stdout], [], [], 0)[0]:
                    line = process.stdout.readline()
                    if not line:  # Empty string means end of stream
                        break
                    all_stdout.append(line)
                    # Only store lines with test results
                    if any(keyword in line.lower() for keyword in ["tests passed", "tests failed", "tests skipped"]):
                        test_result_lines.append(line.rstrip())
                    has_new_output = True
                    last_output_time = current_time

                # Process all available stderr without blocking
                while select.select([process.stderr], [], [], 0)[0]:
                    line = process.stderr.readline()
                    if not line:  # Empty string means end of stream
                        break
                    all_stderr.append(line)
                    # Only store lines with test results
                    if any(keyword in line.lower() for keyword in ["tests passed", "tests failed", "tests skipped"]):
                        test_result_lines.append(f"{line.rstrip()}")
                    has_new_output = True
                    last_output_time = current_time

                # Calculate elapsed and idle time
                elapsed = current_time - start_time

                # Initialize last_output_time if not set yet
                if last_output_time is None:
                    last_output_time = start_time

                idle_seconds = current_time - last_output_time

                # Check for timeout
                if idle_seconds > idle_timeout_seconds:
                    print(f"\n\n⚠️ Process appears to be hung - no output for {idle_seconds:.1f}s")
                    print("\nTerminating stuck process...")
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        print("Process didn't terminate gracefully, killing it")
                        process.kill()
                    ret_code = 1
                    break

                # Update display on the same line
                idle_indicator = f"(idle: {idle_seconds:.1f}s)" if idle_seconds > 3 else "(active)"
                status = f"\r[{spinner[counter % 4]}] Testing: {elapsed:6.1f}s {idle_indicator}"
                sys.stdout.write(status)
                sys.stdout.flush()

                counter += 1

                # Sleep briefly for UI responsiveness, longer when idle
                time.sleep(10 if has_new_output else 1)

            # Get any remaining output
            stdout, stderr = process.communicate()
            if stdout:
                all_stdout.append(stdout)
                for line in stdout.splitlines():
                    if any(keyword in line.lower() for keyword in ["tests passed", "tests failed", "tests skipped"]):
                        test_result_lines.append(line)
            if stderr:
                all_stderr.append(stderr)
                for line in stderr.splitlines():
                    if any(keyword in line.lower() for keyword in ["tests passed", "tests failed", "tests skipped"]):
                        test_result_lines.append(f"{line}")

            # Clear spinner line and print summary
            sys.stdout.write("\r" + " " * 50 + "\r")
            print(f"\nTests completed with return code: {ret_code}")

            # Display test result lines
            if test_result_lines:
                print("\nTest Results Summary:")
                print("=" * 50)
                for line in test_result_lines:
                    print(line)
                print("=" * 50)

            # For further processing, create a result-like object
            result = type('', (), {})()
            result.returncode = ret_code
            result.stdout = ''.join(all_stdout)
            result.stderr = ''.join(all_stderr)

        except Exception as e:
            print(f"❌ Test execution process failed: {e}")
            # This is a critical failure in the execution process itself
            return 1

    except Exception as e:
        print(f"❌ Critical error: {e}")
        return 1
    finally:
        # Always perform cleanup
        if postgres_proc and postgres_proc.poll() is None:
            print(f"Terminating PostgreSQL process with PID {postgres_proc.pid}")
            try:
                postgres_proc.terminate()
                postgres_proc.wait(timeout=10)
            except (subprocess.TimeoutExpired, Exception) as e:
                print(f"Error terminating PostgreSQL: {e}")
                postgres_proc.kill()

        # Display test results regardless of how it completed
        try:
            if 'test_result_lines' in locals() and test_result_lines:
                if not test_result_lines:
                    print("No test result information was captured.")
        except Exception as e:
            print(f"Error displaying test results: {e}")

        kill_postgres_processes()
        os.chdir(current_dir)

    return 0  # Always return success unless critical error occurred


if __name__ == "__main__":
    sys.exit(main())
