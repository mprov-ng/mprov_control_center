# The mPCC's release version.  Its major.minor is the API version: an API
# client built for another major.minor gets 426 Upgrade Required (#452).
# The release workflow refuses a release whose tag isn't v<__version__>.
__version__ = "0.6.1"
API_VERSION = ".".join(__version__.split(".")[:2])
