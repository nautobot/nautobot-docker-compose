"""Development Tasks."""

from distutils.util import strtobool
from time import sleep
import os
import re
import toml
from invoke import Collection, task as invoke_task
from invoke.exceptions import Exit


def is_truthy(arg):
    """Convert "truthy" strings into Booleans.

    Examples:
        >>> is_truthy('yes')
        True
    Args:
        arg (str): Truthy string (True values are y, yes, t, true, on and 1; false values are n, no,
        f, false, off and 0. Raises ValueError if val is anything else.
    """
    if isinstance(arg, bool):
        return arg
    return bool(strtobool(arg))


# Use pyinvoke configuration for default values, see http://docs.pyinvoke.org/en/stable/concepts/configuration.html
# Variables may be overwritten in invoke.yml or by the environment variables INVOKE_NAUTOBOT_xxx
namespace = Collection("nautobot_docker_compose")
namespace.configure(
    {
        "nautobot_docker_compose": {
            "project_name": "nautobot_docker_compose",
            "python_ver": "3.10",
            "nautobot_ver": "2.3.2",
            "local": False,
            "use_django_extensions": True,
            "compose_dir": os.path.join(os.path.dirname(__file__), "environments/"),
            "compose_files": [
                "docker-compose.postgres.yml",
                "docker-compose.base.yml",
                "docker-compose.local.yml",
            ],
        }
    }
)

with open("pyproject.toml", "r", encoding="utf8") as pyproject:
    parsed_toml = toml.load(pyproject)

NAUTOBOT_VERSION = parsed_toml["tool"]["poetry"]["dependencies"]["nautobot"]


def task(function=None, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
    """Task decorator to override the default Invoke task decorator."""

    def task_wrapper(function=None):
        """Wrap invoke.task to add the task to the namespace as well."""
        if args or kwargs:
            task_func = invoke_task(*args, **kwargs)(function)
        else:
            task_func = invoke_task(function)
        namespace.add_task(task_func)
        return task_func

    if function:
        # The decorator was called with no arguments
        return task_wrapper(function)
    # The decorator was called with arguments
    return task_wrapper


def docker_compose(context, command, **kwargs):
    """Run a specific docker-compose command with all appropriate parameters and environment.

    Args:
        context (obj): Used to run specific commands
        command (str): Command string to append to the "docker-compose ..." command, such as "build", "up", etc.
        **kwargs: Passed through to the context.run() call.
    """
    compose_env = {
        "PYTHON_VER": context.nautobot_docker_compose.python_ver,
        "NAUTOBOT_VERSION": NAUTOBOT_VERSION,
    }
    compose_command = f'docker compose --project-name {context.nautobot_docker_compose.project_name} --project-directory "{context.nautobot_docker_compose.compose_dir}"'
    for compose_file in context.nautobot_docker_compose.compose_files:
        compose_file_path = os.path.join(
            context.nautobot_docker_compose.compose_dir, compose_file
        )
        compose_command += f' -f "{compose_file_path}"'
    compose_command += f" {command}"
    print(f'Running docker compose command "{command}"')
    return context.run(compose_command, env=compose_env, **kwargs)


def run_command(context, command, **kwargs):
    """Run a command locally or inside the nautobot container."""
    if is_truthy(context.nautobot_docker_compose.local):
        context.run(command)
    else:
        # Check if nautobot is running, no need to start another nautobot container to run a command
        docker_compose_status = "ps --services --filter status=running"
        results = docker_compose(context, docker_compose_status, hide="out")
        if "nautobot" in results.stdout:
            compose_command = f"exec nautobot {command}"
        else:
            compose_command = f"run --entrypoint '{command}' nautobot"

        docker_compose(context, compose_command, pty=True)


# ------------------------------------------------------------------------------
# BUILD
# ------------------------------------------------------------------------------
@task(
    help={
        "force_rm": "Always remove intermediate containers",
        "cache": "Whether to use Docker's cache when building the image (defaults to enabled)",
    }
)
def build(context, force_rm=False, cache=True):
    """Build Nautobot docker image."""
    command = "build"

    if not cache:
        command += " --no-cache"
    if force_rm:
        command += " --force-rm"

    print(
        f"Building Nautobot {NAUTOBOT_VERSION} with Python {context.nautobot_docker_compose.python_ver}..."
    )
    docker_compose(context, command)

def _get_docker_nautobot_version(context, nautobot_ver=None, python_ver=None):
    """Extract Nautobot version from base docker image."""
    if nautobot_ver is None:
        nautobot_ver = context.nautobot_docker_compose.nautobot_ver
    if python_ver is None:
        python_ver = context.nautobot_docker_compose.python_ver
    dockerfile_path = os.path.join(context.nautobot_docker_compose.compose_dir, "Dockerfile")
    base_image = context.run(f"grep --max-count=1 '^FROM ' {dockerfile_path}", hide=True).stdout.strip().split(" ")[1]
    base_image = base_image.replace(r"${NAUTOBOT_VERSION}", nautobot_ver).replace(r"${PYTHON_VER}", python_ver)
    pip_nautobot_ver = context.run(f"docker run --rm --entrypoint '' {base_image} pip show nautobot", hide=True)
    match_version = re.search(r"^Version: (.+)$", pip_nautobot_ver.stdout.strip(), flags=re.MULTILINE)
    if match_version:
        return match_version.group(1)
    else:
        raise Exit(f"Nautobot version not found in Docker base image {base_image}.")

@task(
    help={
        "check": (
            "If enabled, check for outdated dependencies in the poetry.lock file, "
            "instead of generating a new one. (default: disabled)"
        ),
        "constrain_nautobot_ver": (
            "Run 'poetry add nautobot@[version] --lock' to generate the lockfile, "
            "where [version] is the version installed in the Dockerfile's base image. "
            "Generally intended to be used in CI and not for local development. (default: disabled)"
        ),
        "constrain_python_ver": (
            "When using `constrain_nautobot_ver`, further constrain the nautobot version "
            "to python_ver so that poetry doesn't complain about python version incompatibilities. "
            "Generally intended to be used in CI and not for local development. (default: disabled)"
        ),
    }
)
def lock(context, check=False, constrain_nautobot_ver=False, constrain_python_ver=False):
    """Generate poetry.lock file."""
    if constrain_nautobot_ver:
        docker_nautobot_version = _get_docker_nautobot_version(context)
        # docker_nautobot_version = context.nautobot_docker_compose.nautobot_ver
        command = f"poetry add --lock nautobot@{docker_nautobot_version}"
        if constrain_python_ver:
            command += f" --python {context.nautobot_docker_compose.python_ver}"
    else:
        command = f"poetry {'check' if check else 'lock --no-update'}"
    run_command(context, command)


# ------------------------------------------------------------------------------
# START / STOP / DEBUG
# ------------------------------------------------------------------------------
@task
def debug(context):
    """Start Nautobot and its dependencies in debug mode."""
    print("Starting Nautobot in debug mode...")
    docker_compose(context, "up")


@task
def start(context):
    """Start Nautobot and its dependencies in detached mode."""
    print("Starting Nautobot in detached mode...")
    docker_compose(context, "up --detach")


@task
def restart(context):
    """Gracefully restart all containers."""
    print("Restarting Nautobot...")
    docker_compose(context, "restart")


@task
def stop(context):
    """Stop Nautobot and its dependencies."""
    print("Stopping Nautobot...")
    docker_compose(context, "down")


@task
def destroy(context):
    """Destroy all containers and volumes."""
    print("Destroying Nautobot...")
    docker_compose(context, "down --volumes")


# ------------------------------------------------------------------------------
# ACTIONS
# ------------------------------------------------------------------------------
@task
def nbshell(context):
    """Launch an interactive nbshell session."""
    if context.nautobot_docker_compose.use_django_extensions:
        command = "nautobot-server shell_plus"
    else:
        command = "nautobot-server nbshell"

    run_command(context, command, pty=True)


@task
def cli(context):
    """Launch a bash shell inside the running Nautobot container."""
    run_command(context, "bash")


@task(
    help={
        "user": "name of the superuser to create (default: admin)",
    }
)
def createsuperuser(context, user="admin"):
    """Create a new Nautobot superuser account (default: "admin"), will prompt for password."""
    command = f"nautobot-server createsuperuser --username {user}"

    run_command(context, command)


@task
def migrate(context):
    """Perform migrate operation in Django."""
    command = "nautobot-server migrate"

    run_command(context, command)


@task
def post_upgrade(context):
    """
    Nautobot common post-upgrade operations using a single entrypoint.

    This will run the following management commands with default settings, in order:

    - migrate
    - trace_paths
    - collectstatic
    - remove_stale_contenttypes
    - clearsessions
    - invalidate all
    """
    command = "nautobot-server post_upgrade"

    run_command(context, command)


@task
def import_nautobot_data(context):
    """Import nautobot_data.json."""
    # This task expects to be run in the docker container for now
    context.nautobot_docker_compose.local = False
    copy_cmd = f"docker cp nautobot_data.json {context.nautobot_docker_compose.project_name}_nautobot_1:/tmp/nautobot_data.json"
    import_cmd = "nautobot-server import_nautobot_json /tmp/nautobot_data.json 2.10.4"
    print("Starting Nautobot")
    start(context)
    print("Copying Nautobot data to container")
    context.run(copy_cmd)
    print("Starting Import")
    print(import_cmd)
    run_command(context, import_cmd)


@task
def db_export(context):
    """Export the database from the dev environment to nautobot.sql."""
    docker_compose(context, "up -d db")
    sleep(2)  # Wait for the database to be ready

    print("Exporting the database as an SQL dump...")
    if "docker-compose.mysql.yml" in context.nautobot_docker_compose.compose_files:
        export_cmd = 'exec db sh -c "mysqldump -u \${NAUTOBOT_DB_USER} –p \${NAUTOBOT_DB_PASSWORD} \${NAUTOBOT_DB_NAME} nautobot > /tmp/nautobot.sql"'  # noqa: W605 pylint: disable=anomalous-backslash-in-string
        copy_cmd = f"docker cp {context.nautobot_docker_compose.project_name}-db-1:/tmp/nautobot.sql nautobot.sql"
    else:
        export_cmd = 'exec db sh -c "pg_dump -h localhost -d \${NAUTOBOT_DB_NAME} -U \${NAUTOBOT_DB_USER} > /tmp/nautobot.sql"'  # noqa: W605 pylint: disable=anomalous-backslash-in-string
        copy_cmd = f"docker cp {context.nautobot_docker_compose.project_name}-db-1:/tmp/nautobot.sql nautobot.sql"
    docker_compose(context, export_cmd, pty=True)
    print("Copying the SQL Dump locally...")
    context.run(copy_cmd)


@task
def db_import(context):
    """Install the backup of Nautobot db into development environment."""
    print("Importing Database into Development...\n")

    print("Starting Postgres for DB import...\n")
    docker_compose(context, "up -d db")
    sleep(2)

    print("Copying DB Dump to DB container...\n")
    if "docker-compose.mysql.yml" in context.nautobot_docker_compose.compose_files:
        copy_cmd = f"docker cp nautobot.sql {context.nautobot_docker_compose.project_name}-db-1:/tmp/nautobot.sql"
        import_cmd = 'exec db sh -c "mysql -u \${NAUTOBOT_DB_USER} –p \${NAUTOBOT_DB_PASSWORD} < /tmp/nautobot.sql"'  # noqa: W605 pylint: disable=anomalous-backslash-in-string
    else:
        copy_cmd = f"docker cp nautobot.sql {context.nautobot_docker_compose.project_name}-db-1:/tmp/nautobot.sql"
        import_cmd = 'exec db sh -c "psql -h localhost -U \${NAUTOBOT_DB_USER} < /tmp/nautobot.sql"'  # noqa: W605 pylint: disable=anomalous-backslash-in-string
    context.run(copy_cmd)

    print("Importing DB...\n")
    docker_compose(context, import_cmd, pty=True)

# ------------------------------------------------------------------------------
# TESTS
# ------------------------------------------------------------------------------

@task(
    help={
        "keepdb": "save and re-use test database between test runs for faster re-testing.",
        "label": "specify a directory or module to test instead of running all Nautobot tests",
        "failfast": "fail as soon as a single test fails don't run the entire test suite",
        "buffer": "Discard output from passing tests",
        "pattern": "Run specific test methods, classes, or modules instead of all tests",
        "verbose": "Enable verbose test output.",
    }
)
def unittest(  # noqa: PLR0913
    context,
    keepdb=False,
    label="tests",
    failfast=False,
    buffer=True,
    pattern="",
    verbose=False,
):
    """Run Nautobot unit tests."""
    command = f"coverage run --module nautobot.core.cli test {label}"

    if keepdb:
        command += " --keepdb"
    if failfast:
        command += " --failfast"
    if buffer:
        command += " --buffer"
    if pattern:
        command += f" -k='{pattern}'"
    if verbose:
        command += " --verbosity 2"

    run_command(context, command)

@task
def yamllint(context):
    """Run yamllint to validate formatting adheres to NTC defined YAML standards.

    Args:
        context (obj): Used to run specific commands
    """
    command = "yamllint . --format standard"
    run_command(context, command)
