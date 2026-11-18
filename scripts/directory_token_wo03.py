"""
CAT-WO-03 · one-off consent for the staff step of pipeline/subject_wo03.py (Subject (person) on personnel documents).

  py app\\scripts\\directory_token_wo03.py            (run from C:\\DriveCatalog, where client_secret.json lives)

Opens the browser for ONE scope, directory.readonly (read the Workspace directory: names and work emails), with the
same OAuth client as the crawl. Writes the token to %TEMP%\\catwo03_directory_token.json (outside the repo and outside
C:\\DriveCatalog) and prints only that path. The subject step never refreshes it (CISO review): use it within the hour,
then delete it:

  py app\\pipeline\\subject_wo03.py --db-url-file <url file> [--release] --directory-token %TEMP%\\catwo03_directory_token.json --apply
  del %TEMP%\\catwo03_directory_token.json

The nightly run does not use this token; without it the staff step is reported as skipped and the last values are kept.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/directory.readonly"]


def main():
    if not os.path.exists("client_secret.json"):
        raise SystemExit("run from C:\\DriveCatalog (client_secret.json not found here)")
    c = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES).run_local_server(port=0)
    out = os.path.join(os.environ.get("TEMP", "."), "catwo03_directory_token.json")
    with open(out, "w") as f:
        f.write(c.to_json())
    print(f"token written: {out} (expires in about an hour; delete it after the staff step)")


if __name__ == "__main__":
    main()
