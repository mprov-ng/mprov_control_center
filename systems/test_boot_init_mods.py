import os
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

SCRIPT = Path(settings.BASE_DIR) / "static" / "mprov_boot_init.sh"
INIT_MODS = Path("/tmp/init_mods")


class BootInitialModsTests(SimpleTestCase):
  """ static/mprov_boot_init.sh loads the mprov_initial_mods list from the
  kernel command line, before the drivers it finds by PCI class, and records
  the ones that loaded in /tmp/init_mods (#372). """

  def setUp(self):
    text = SCRIPT.read_text()
    self.function = re.search(r"^load_initial_mods\(\) \{.*?^\}", text, re.S | re.M).group(0)
    # a modprobe that knows e1000, tg3 and mlx5_core, and logs what it was asked for.
    self.bin = tempfile.mkdtemp()
    self.log = os.path.join(self.bin, "modprobe.log")
    with open(os.path.join(self.bin, "modprobe"), "w") as f:
      f.write(f'#!/bin/bash\necho "$1" >> {self.log}\ncase "$1" in e1000|tg3|mlx5_core) exit 0 ;; *) exit 1 ;; esac\n')
    os.chmod(os.path.join(self.bin, "modprobe"), 0o755)
    INIT_MODS.unlink(missing_ok=True)
    self.addCleanup(INIT_MODS.unlink, missing_ok=True)

  def load(self, mods):
    INIT_MODS.write_text("")
    result = subprocess.run(["bash", "-c", f'{self.function}\nload_initial_mods "$1"', "bash", mods],
                            capture_output=True, text=True, env=dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}"))
    asked = Path(self.log).read_text().split() if os.path.exists(self.log) else []
    return result, asked, INIT_MODS.read_text()

  def test_loads_each_listed_module_and_records_it(self):
    result, asked, recorded = self.load("e1000,tg3,mlx5_core")
    self.assertEqual(result.returncode, 0)
    self.assertEqual(asked, ["e1000", "tg3", "mlx5_core"])
    self.assertEqual(recorded, "e1000,tg3,mlx5_core,")

  def test_a_module_that_doesnt_load_is_skipped_with_a_warning(self):
    result, asked, recorded = self.load("e1000,not_a_module,,tg3")
    self.assertEqual(result.returncode, 0)
    self.assertEqual(asked, ["e1000", "not_a_module", "tg3"])
    self.assertEqual(recorded, "e1000,tg3,")
    self.assertIn("(not_a_module not loaded)", result.stderr)

  def test_an_empty_list_loads_nothing(self):
    result, asked, recorded = self.load("")
    self.assertEqual(result.returncode, 0)
    self.assertEqual(asked, [])
    self.assertEqual(recorded, "")

  def test_the_list_loads_before_the_pci_drivers(self):
    text = SCRIPT.read_text()
    self.assertIn('load_initial_mods "$MPROV_INITIAL_MODS"', text)
    self.assertLess(text.index('load_initial_mods "$MPROV_INITIAL_MODS"'), text.index("Loading network drivers"))
    # after the list is read from the command line, and after /tmp/init_mods is emptied
    self.assertLess(text.index("MPROV_INITIAL_MODS=$(get_kcmdline_opt mprov_initial_mods)"),
                    text.index('load_initial_mods "$MPROV_INITIAL_MODS"'))
    self.assertLess(text.index('echo -n "" > /tmp/init_mods'), text.index('load_initial_mods "$MPROV_INITIAL_MODS"'))
