""" What a job server running a bmc-rotate job reads and reports (#486).

- GET /bmcrotations/<id>/secret/: the BMC's address and the credentials to
  use.  Never logged by either side.
- POST /bmcrotations/<id>/result/: {status, method, verified, tls_verified,
  error}.  The mPCC stores exactly the pair the job server verified.

Only the job server whose certificate claimed the request's job, while that
job is RUNNING. """
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from bmcrotate import logic
from bmcrotate.models import BMCRotation
from common.permissions import MProvPermission


class RotationView(APIView):
    permission_classes = [MProvPermission]

    def rotation(self, request, pk):
        """ (rotation, None) for the caller's own running request, else (None, error Response). """
        from pki.models import AgentCredential
        credential = request.auth if isinstance(request.auth, AgentCredential) else None
        if credential is None or credential.kind != AgentCredential.JOBSERVER:
            return None, Response({"detail": "Only a job server's own certificate may do this."},
                                  status=status.HTTP_403_FORBIDDEN)
        rotation = BMCRotation.objects.select_related("bmc__system", "job").filter(pk=pk).first()
        if rotation is None:
            return None, Response({"detail": "No such request."}, status=status.HTTP_404_NOT_FOUND)
        if rotation.status not in (BMCRotation.PENDING, BMCRotation.RUNNING):
            return None, Response({"detail": "This request is finished."}, status=status.HTTP_409_CONFLICT)
        job = rotation.job
        if job is None or job.jobserver_id != credential.jobserver_id or job.status_id != logic.RUNNING:
            return None, Response({"detail": "Not a job this job server is running."},
                                  status=status.HTTP_403_FORBIDDEN)
        return rotation, None


class RotationSecretView(RotationView):
    def get(self, request, pk):
        rotation, refusal = self.rotation(request, pk)
        if refusal:
            return refusal
        if rotation.status == BMCRotation.PENDING:
            rotation.status = BMCRotation.RUNNING
            rotation.save(update_fields=["status"])
        return Response(logic.secret(rotation))


class RotationResultView(RotationView):
    def post(self, request, pk):
        rotation, refusal = self.rotation(request, pk)
        if refusal:
            return refusal
        data = request.data if isinstance(request.data, dict) else {}
        if data.get("status") not in logic.RESULT_STATUSES:
            return Response({"status": f"Must be one of {', '.join(sorted(logic.RESULT_STATUSES))}."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"stored": logic.apply_result(rotation, data)})
