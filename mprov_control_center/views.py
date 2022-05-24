from common.views import MProvView

# Default view for the index.
class IndexAPIView(MProvView):
    """
# Welcome to mProv Control Center

Welcome to the mProv Control Center API.  What you see here is the documentation for how mPCC's RESTful API works.


Chances are good you are looking for the [Admin](/admin/) section to get in and modify stuff.  If, 
however, you are looking for the documentation on how to use this API, you should probably try clicking on 
one of the following links.   Each link is a section of the API that corresponds to a section of the admin 
interface.  It will give you documentation on how to use that section of the api.

* [/distros/](/distros/) .
* [/images/](/images/)  .
* [/jobs/](/jobs/)  .
* [/jobmodules/](/jobmodules/)  .
* [/jobservers/](/jobservers/)  .
* [/kernels/](/kernels/)  .
* [/networkinterfaces/](/networkinterfaces/)   .
* [/networks/](/networks/)  .
* [/networktypes/](/networktypes/)  .
* [/repos/](/repos/)  .
* [/scripts/](/scripts/)
* [/switches/](/switches/)  .
* [/switchports/](/switchports/)  .
* [/systemgroups/](/systemgroups/)  .
* [/systemimages/](/systemimages/)  .
* [/systems/](/systems/)  .
* [/systems/register](/systems/register)  .

    """
    template = 'docs.html'