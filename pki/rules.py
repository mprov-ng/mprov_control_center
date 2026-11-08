""" What each kind of agent may do through the API (#381).

A job server's or system's certificate (pki.authentication) only reaches
the endpoints, objects and fields that agent needs.  The rules come from a
check of every client (mprov_jobserver, its script runner, mprov_scripts'
post-boot scripts, the stateful installer and genNetworkInterfaces.py):

- a system may read and update only itself: its own row (?self), its own
  network interfaces and their networks, and its own BMC entries;
- a job server may read the inventory (DHCP, DNS, genders and image builds
  need all of it), and write only its own registration and heartbeats, the
  jobs it claims, and itself as a host of images and repos.

Anything not listed is refused.  The same system rules apply to the shared
API key in MPROV_SHARED_KEY_MODE=nodes, with the system found from the
caller's address.
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

# keys any GET may add without changing what it returns
HARMLESS_QUERY = {"format"}


@dataclass
class Rule:
    """ One thing an agent may do: methods on a path (a regex over the whole path),
    with the query keys allowed and needed, the body keys a write may send, and
    an optional ownership check(agent, request, match). """
    methods: tuple
    path: str
    # the query keys allowed (besides HARMLESS_QUERY), or None for any
    query: Optional[set] = None
    # query keys that must be there
    needs: set = field(default_factory=set)
    # the body keys allowed in a write, or None for any
    fields: Optional[set] = None
    # check(agent, request, match) -> bool, for object ownership
    check: Optional[Callable] = None

    def __post_init__(self):
        self.pattern = re.compile("^" + self.path + "$")

    def allows(self, agent, request):
        """ True if this request matches the rule in every respect. """
        if request.method not in self.methods:
            return False
        match = self.pattern.match(request.path)
        if match is None:
            return False
        keys = set(request.query_params.keys())
        if not self.needs <= keys:
            return False
        if self.query is not None and not keys <= (self.query | self.needs | HARMLESS_QUERY):
            return False
        if self.fields is not None and request.method in ("POST", "PATCH", "PUT"):
            data = request.data
            if not isinstance(data, dict) or not set(data.keys()) <= self.fields:
                return False
        return self.check is None or bool(self.check(agent, request, match))


def _int(value):
    """ value as an int, or None. """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _body(request, key):
    """ key from the request body, or None if the body isn't an object. """
    return request.data.get(key) if isinstance(request.data, dict) else None


# ---- systems --------------------------------------------------------------

def self_is_itself(system, request, match):
    """ ?self is resolved from the caller's address by the views; make sure
    that's this system (two systems could share an address). """
    from common.permissions import system_from_address
    return system_from_address(request) == system


def own_system_query(system, request, match):
    """ ?system=<itself> for the lists that take one. """
    value = request.query_params.get("system")
    return value is None or _int(value) == system.pk


def own_hostname(system, request, match):
    """ ?hostname= its own hostname or one of its interfaces'. """
    value = request.query_params.get("hostname")
    if value is None:
        return True
    return value == system.hostname or system.networkinterface_set.filter(hostname=value).exists()


def own_nic(system, request, match):
    """ The network interface in the path is one of its own. """
    return system.networkinterface_set.filter(pk=_int(match.group("pk"))).exists()


def own_nic_network(system, request, match):
    """ The network in the path is one of its own interfaces' networks. """
    return system.networkinterface_set.filter(network_id=_int(match.group("pk"))).exists()


def own_bmc(system, request, match):
    """ The BMC entry in the path is its own. """
    from systems.models import SystemBMC
    return SystemBMC.objects.filter(pk=_int(match.group("pk")), system=system).exists()


def nic_list(system, request, match):
    """ The interface list is filtered to its own interfaces, by ?system= or
    ?hostname=. """
    keys = set(request.query_params.keys())
    # one of the two filters, so the list is only its own interfaces
    if not keys & {"system", "hostname"}:
        return False
    return own_system_query(system, request, match) and own_hostname(system, request, match)


def bmc_list(system, request, match):
    """ The BMC list is filtered to its own entries, by ?self or ?system=. """
    keys = set(request.query_params.keys())
    if "self" in keys:
        return "system" not in keys and self_is_itself(system, request, match)
    return "system" in keys and own_system_query(system, request, match)


PK = r"(?P<pk>[^/]+)"

SYSTEM_RULES = [
    Rule(("GET",), r"/", query=set()),
    # the script runner, localTempDisk.py and the stateful installer
    Rule(("GET",), r"/systems/", needs={"self"}, query={"detail"}, check=self_is_itself),
    # setupBMC.py
    Rule(("GET",), r"/systems/", needs={"hostname"}, query={"detail"}, check=own_hostname),
    # the stateful installer ({"netboot": false}) and report_booted.py
    # ({"booted": true}, then {"serial": ...}, #60)
    Rule(("POST",), r"/systems/", needs={"self"}, query=set(), fields={"netboot", "booted", "serial"},
         check=self_is_itself),
    # genNetworkInterfaces.py (?system=) and register_IPv6_ll.py (?hostname=)
    Rule(("GET",), r"/networkinterfaces/", query={"system", "hostname", "detail"}, check=nic_list),
    Rule(("GET",), rf"/networkinterfaces/{PK}/", query={"detail"}, check=own_nic),
    Rule(("PATCH",), rf"/networkinterfaces/{PK}/", query=set(), fields={"id", "ipv6ll"}, check=own_nic),
    Rule(("GET",), rf"/networks/{PK}/", query={"detail"}, check=own_nic_network),
    # setupBMC.py
    Rule(("GET",), r"/systembmcs/", query={"self", "system", "detail"}, check=bmc_list),
    Rule(("GET",), rf"/systembmcs/{PK}/", query={"detail"}, check=own_bmc),
    Rule(("PATCH",), rf"/systembmcs/{PK}/", query=set(), fields={"id", "mac", "ipv6ll"}, check=own_bmc),
    # renewing its own certificate (pki.views.RenewView)
    Rule(("POST",), r"/enroll/renew/", query=set(), fields={"csr"}),
]


# ---- job servers ----------------------------------------------------------

def registers_itself(jobserver, request, match):
    """ POST /jobservers/ only for its own host ID. """
    sent = _body(request, "host_id")
    return jobserver.host_id is not None and sent == jobserver.host_id


def its_own_row(jobserver, request, match):
    """ The job server in the path is itself. """
    return _int(match.group("pk")) == jobserver.pk


def claims_for_itself(jobserver, request, match):
    """ A job claim names itself as the job server. """
    return _int(_body(request, "jobserver")) == jobserver.pk


def its_job(jobserver, request, match):
    """ A job that's unclaimed or its own, updated as its own. """
    from jobqueue.models import Job
    job = Job.objects.filter(pk=_int(match.group("pk"))).values_list("jobserver_id", flat=True)
    if not job.exists():
        return False
    if job.first() not in (None, jobserver.pk):
        return False
    sent = _body(request, "jobserver")
    return sent is None or _int(sent) == jobserver.pk


def adds_itself(key):
    """ An ?addjs PATCH that lists this job server among the hosts. """
    def check(jobserver, request, match):
        hosts = _body(request, key)
        return isinstance(hosts, list) and jobserver.pk in [_int(h) for h in hosts]
    return check


def only_itself(key):
    """ A PATCH whose host list (the body's key) is exactly this job server. """
    def check(jobserver, request, match):
        hosts = _body(request, key)
        return isinstance(hosts, list) and [_int(h) for h in hosts] == [jobserver.pk]
    return check


JOBSERVER_RULES = [
    # reads of the inventory: DHCP, DNS, PXE, genders, image and repo builds
    Rule(("GET",), r"/(?!power/|datamodel/).*"),
    Rule(("POST",), r"/jobservers/", check=registers_itself),
    Rule(("POST",), rf"/jobservers/{PK}/heartbeat/", fields={"address"}, check=its_own_row),
    Rule(("POST",), rf"/jobs/{PK}/claim/", fields={"jobserver"}, check=claims_for_itself),
    Rule(("PATCH",), rf"/jobs/{PK}/", query=set(),
         fields={"id", "pk", "status", "start_time", "end_time", "jobserver", "return_code"}, check=its_job),
    # follow-up jobs an image build queues
    Rule(("POST",), r"/jobs/", query=set()),
    # a bmc-rotate job's result (#486); bmcrotate.views checks it's its own job
    Rule(("POST",), rf"/bmcrotations/{PK}/result/", query=set(),
         fields={"status", "method", "verified", "tls_verified", "error"}),
    Rule(("PATCH",), rf"/systemimages/{PK}/", needs={"addjs"}, query=set(),
         fields={"slug", "jobservers", "version"}, check=adds_itself("jobservers")),
    Rule(("PATCH",), rf"/repos/{PK}/", needs={"addjs"}, query=set(),
         fields={"id", "hosted_by"}, check=adds_itself("hosted_by")),
    # repo-update marks itself the repo's host
    Rule(("PATCH",), rf"/repos/{PK}/", query=set(), fields={"id", "hosted_by"}, check=only_itself("hosted_by")),
    # the rhel image/repo modules register their OS type
    Rule(("POST",), r"/ostypes/", query=set(), fields={"slug", "name"}),
    Rule(("POST",), r"/enroll/renew/", query=set(), fields={"csr"}),
    # a short-lived credential for the script runner in an image it builds
    Rule(("POST",), r"/enroll/build/", query=set(), fields={"csr", "image"}),
]


# ---- image builds --------------------------------------------------------

def its_image(image, request, match):
    """ The image in the path is the one being built. """
    return match.group("pk") == image.slug


BUILD_RULES = [
    Rule(("GET",), r"/", query=set()),
    # the script runner inside the image (script_runner.py -i <slug>)
    Rule(("GET",), rf"/systemimages/{PK}/", query={"detail"}, check=its_image),
]


def build_allows(image, request):
    """ True if an image-build credential for image may make this request. """
    return any(rule.allows(image, request) for rule in BUILD_RULES)


def system_allows(system, request):
    """ True if a system's credential (or the shared key in nodes mode) may make
    this request. """
    return any(rule.allows(system, request) for rule in SYSTEM_RULES)


def jobserver_allows(jobserver, request):
    """ True if a job server's credential may make this request. """
    return any(rule.allows(jobserver, request) for rule in JOBSERVER_RULES)
