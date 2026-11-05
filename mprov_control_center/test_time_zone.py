import io
from contextlib import redirect_stderr

from django.test import SimpleTestCase

from mprov_control_center.settings import env_time_zone


class EnvTimeZoneTests(SimpleTestCase):
  """ The mPCC's time zone comes from TIME_ZONE, or else TZ, which is all
  mprov-compose sets, or else UTC; a value that isn't a zone name gives UTC
  and a warning.  It used to ignore TZ, so under compose Django ran, and
  reset the process clock, in UTC (#456). """

  def zone(self, **environ):
    err = io.StringIO()
    with redirect_stderr(err):
      zone = env_time_zone(environ)
    return zone, err.getvalue()

  def test_neither_set_is_utc(self):
    self.assertEqual(self.zone(), ("UTC", ""))

  def test_time_zone_wins_over_tz(self):
    self.assertEqual(self.zone(TIME_ZONE="Europe/London", TZ="America/New_York"), ("Europe/London", ""))

  def test_tz_when_time_zone_unset(self):
    self.assertEqual(self.zone(TZ="America/New_York"), ("America/New_York", ""))
    self.assertEqual(self.zone(TIME_ZONE="", TZ="America/New_York"), ("America/New_York", ""))

  def test_tz_leading_colon_is_stripped(self):
    self.assertEqual(self.zone(TZ=":America/New_York"), ("America/New_York", ""))

  def test_tz_that_isnt_a_zone_name_falls_back_to_utc(self):
    for tz in ("EST5EDT,M3.2.0,M11.1.0", "Not/AZone", "../etc/passwd"):
      zone, err = self.zone(TZ=tz)
      self.assertEqual(zone, "UTC", tz)
      self.assertIn("Warning", err, tz)

  def test_time_zone_leading_colon_is_stripped(self):
    self.assertEqual(self.zone(TIME_ZONE=":Europe/London"), ("Europe/London", ""))

  def test_time_zone_that_isnt_a_zone_name_falls_back_to_utc(self):
    # mprov-compose may set TIME_ZONE=${TZ}, so it can carry a POSIX TZ too.
    for tz in ("EST5EDT,M3.2.0,M11.1.0", "Not/AZone"):
      zone, err = self.zone(TIME_ZONE=tz, TZ="America/New_York")
      self.assertEqual(zone, "UTC", tz)
      self.assertIn("TIME_ZONE", err, tz)
