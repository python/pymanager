import json
import os
import sys

from urllib.request import urlopen, Request


DIRECTORY_ID = os.environ["MSSTORE_TENANT_ID"]
CLIENT_ID = os.environ["MSSTORE_CLIENT_ID"]
CLIENT_SECRET = os.environ["MSSTORE_CLIENT_SECRET"]
SELLER_ID = os.environ["MSSTORE_SELLER_ID"]
APP_ID = os.environ["MSSTORE_APP_ID"]

PATCH_JSON = os.environ["PATCH_JSON"]
with open(PATCH_JSON, "rb") as f:
    patch_data = json.load(f)


SERVICE_URL = "https://manage.devcenter.microsoft.com/v1.0/my/"

################################################################################
# Get auth token/header
################################################################################

OAUTH_URL = f"https://login.microsoftonline.com/{DIRECTORY_ID}/oauth2/v2.0/token"
SERVICE_SCOPE = "https://manage.devcenter.microsoft.com/.default"

reqAuth = Request(
    OAUTH_URL,
    method="POST",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data=(f"grant_type=client_credentials&client_id={CLIENT_ID}&" +
          f"client_secret={CLIENT_SECRET}&scope={SERVICE_SCOPE}").encode("utf-8"),
)

with urlopen(reqAuth) as r:
    jwt = json.loads(r.read())

auth = {"Authorization": f"Bearer {jwt['access_token']}"}

################################################################################
# Get application data (for current submission)
################################################################################

reqApps = Request(f"{SERVICE_URL}applications/{APP_ID}", method="GET", headers=auth)
print("Getting application data from", reqApps.full_url)
with urlopen(reqApps) as r:
    app_data = json.loads(r.read())

submission_url = app_data["pendingApplicationSubmission"]["resourceLocation"]

################################################################################
# Get current submission data
################################################################################

reqSubmission = Request(f"{SERVICE_URL}{submission_url}", method="GET", headers=auth)
print("Getting submission data from", reqSubmission.full_url)
with urlopen(reqSubmission) as r:
    sub_data = json.loads(r.read())

################################################################################
# Patch submission data
################################################################################

if patch_data:
    def _patch(target, key, src):
        if key.startswith("#"):
            return
        if isinstance(src, dict):
            for k, v in src.items():
                _patch(target.setdefault(key, {}), k, v)
        else:
            target[key] = src

    for k, v in patch_data.items():
        _patch(sub_data, k, v)

################################################################################
# Update submission data
################################################################################

reqUpdate = Request(f"{SERVICE_URL}{submission_url}", method="PUT",
    headers={**auth, "Content-Type": "application/json; charset=utf-8"},
    data=json.dumps(sub_data).encode("utf-8"))
print("Updating submission data at", reqUpdate.full_url)
with urlopen(reqUpdate) as r:
    new_data = r.read()

new_data.pop("fileUploadUrl", None)
print("Current submission metadata:")
print(json.dumps(new_data, indent=2))
