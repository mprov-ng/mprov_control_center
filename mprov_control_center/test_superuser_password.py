import os
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD_SCRIPT = os.path.join(REPO_ROOT, "install_scripts", "superuser_password.sh")


def read(*parts):
  with open(os.path.join(REPO_ROOT, *parts)) as f:
    return f.read()


class NoBakedSuperuserPasswordTests(unittest.TestCase):
  """The image must not ship default superuser credentials (#317)."""

  def test_dockerfile_does_not_bake_superuser_password(self):
    # no assignment of any value to the password var (comments may explain why)
    self.assertNotIn("DJANGO_SUPERUSER_PASSWORD=", read("Dockerfile"))

  def test_entrypoint_does_not_write_default_password(self):
    self.assertNotIn("DJANGO_SUPERUSER_PASSWORD=admin",
                     read("install_scripts", "init_mpcc.sh"))

  def test_entrypoint_resolves_password_before_creating_superuser(self):
    text = read("install_scripts", "init_mpcc.sh")
    self.assertIn("superuser_password.sh", text)
    self.assertLess(text.index("superuser_password.sh"),
                    text.index("createsuperuser"))

  def test_image_env_has_no_default_password(self):
    env_path = os.path.join(REPO_ROOT, ".env")
    if not os.path.exists(env_path):
      self.skipTest(".env only exists inside the built image")
    for line in open(env_path):
      name, _, value = line.strip().partition("=")
      if name == "DJANGO_SUPERUSER_PASSWORD":
        self.assertNotEqual(value.strip("'\""), "admin",
                            "the built image bakes a default superuser password")


class SuperuserPasswordScriptTests(unittest.TestCase):
  """install_scripts/superuser_password.sh generates, persists and protects
  the first-run superuser password (#317)."""

  def run_script(self, etc_dir, extra_env=None):
    env = dict(os.environ)
    env["MPROV_ETC_DIR"] = etc_dir
    env.pop("DJANGO_SUPERUSER_PASSWORD", None)
    if extra_env:
      env.update(extra_env)
    # init_mpcc.sh sources the script, so exercise that exact contract:
    # after sourcing, DJANGO_SUPERUSER_PASSWORD must be exported.
    return subprocess.run(
      ["bash", "-c", '. "$1" && printf %s "$DJANGO_SUPERUSER_PASSWORD"',
       "init_mpcc_sh", PASSWORD_SCRIPT],
      capture_output=True, text=True, env=env)

  def test_generates_a_random_password_when_unset(self):
    with tempfile.TemporaryDirectory() as etc:
      proc = self.run_script(etc)
      self.assertEqual(proc.returncode, 0, proc.stderr)
      password = proc.stdout
      self.assertNotEqual(password, "admin")
      self.assertGreaterEqual(len(password), 24)
      self.assertIn(password, proc.stderr)  # shown to the operator once
      saved = os.path.join(etc, "superuser_password")
      self.assertTrue(os.path.exists(saved))
      self.assertEqual(open(saved).read().strip(), password)

  def test_generated_passwords_differ_between_installs(self):
    with tempfile.TemporaryDirectory() as etc_a, tempfile.TemporaryDirectory() as etc_b:
      first = self.run_script(etc_a).stdout
      second = self.run_script(etc_b).stdout
      self.assertNotEqual(first, second)

  def test_saved_password_file_is_owner_only(self):
    with tempfile.TemporaryDirectory() as etc:
      self.run_script(etc)
      mode = os.stat(os.path.join(etc, "superuser_password")).st_mode & 0o777
      self.assertEqual(oct(mode), oct(0o600))

  def test_restart_reuses_the_saved_password(self):
    with tempfile.TemporaryDirectory() as etc:
      first = self.run_script(etc).stdout
      second = self.run_script(etc)
      self.assertEqual(second.stdout, first)
      self.assertNotIn("shown once", second.stderr)

  def test_operator_password_wins_and_saves_nothing(self):
    with tempfile.TemporaryDirectory() as etc:
      proc = self.run_script(etc, {"DJANGO_SUPERUSER_PASSWORD": "operator-secret-1"})
      self.assertEqual(proc.stdout, "operator-secret-1")
      self.assertFalse(os.path.exists(os.path.join(etc, "superuser_password")))


if __name__ == "__main__":
  unittest.main()
