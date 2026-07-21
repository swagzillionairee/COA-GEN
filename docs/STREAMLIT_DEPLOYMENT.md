# Deploy COA Generator 0.3.0 on Streamlit Community Cloud

This edition runs as a normal website. Visitors use a URL and do not install an
`.exe`, Python, or any dependencies on their computers.

## What you need

- A GitHub account
- A Streamlit Community Cloud account connected to GitHub
- The complete `coa-generator` project folder

The deployed app uses `streamlit_app.py` as its entry point and
`requirements.txt` for its runtime packages.

## 1. Create a GitHub repository

1. Sign in to GitHub and create a new repository.
2. Keep it private if the reports or branding are sensitive.
3. Upload the **contents** of the `coa-generator` folder to the repository root.
4. Confirm the repository root contains at least:

   ```text
   streamlit_app.py
   app.py
   requirements.txt
   coa/
   assets/
   templates/
   .streamlit/config.toml
   ```

Do not upload `.venv`, `.venv-build`, `build`, `dist`, or a real
`.streamlit/secrets.toml` file.

## 2. Create the Streamlit app

1. Open https://share.streamlit.io and select **Create app**.
2. Choose **Yup, I have an app**.
3. Select the GitHub repository and branch.
4. Enter `streamlit_app.py` as the file path.
5. Choose the app URL you want.
6. Open **Advanced settings** and select Python 3.12.

## 3. Protect access

For the built-in password gate, add this in the Advanced settings **Secrets** box:

```toml
APP_PASSWORD = "use-a-long-unique-password-here"
```

Do not put the real password in GitHub. You can also use Streamlit Community
Cloud's private sharing controls. For sensitive use, enable private sharing even
when the in-app password is configured.

## 4. Deploy

Select **Deploy**. The first build installs the PDF and image dependencies and
can take several minutes. When the app is ready, open its `streamlit.app` URL.

To update the site later, edit the GitHub repository and push the change.
Streamlit Community Cloud redeploys from the repository automatically.

## Important hosted behavior

- Users download PDFs, JSON scenarios, and batch ZIPs through the browser.
- Uploaded images and generated documents are kept in memory for the active session.
- Custom templates and report-number history stored on the server are temporary and
  may disappear after an app reboot, sleep cycle, or redeploy.
- Download the current source JSON whenever a report or template must be preserved.
- Multiple visitors use the same hosted server process. Use private sharing or the
  password gate and avoid treating server-side numbering as a permanent central ledger.
- The Windows `.exe` build remains available and continues to store its local data in
  `%LOCALAPPDATA%\COAGenerator`.

## Local test of the website entry point

From the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Optional local password test:

```powershell
$env:COA_APP_PASSWORD = "temporary-test-password"
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Remove that PowerShell environment variable afterward with:

```powershell
Remove-Item Env:COA_APP_PASSWORD
```

## Troubleshooting

- **Module not found:** confirm `requirements.txt` is in the repository root next
  to `streamlit_app.py`, then reboot the app from its Streamlit settings.
- **App never becomes healthy:** confirm the entry point is exactly
  `streamlit_app.py`, not `launcher.py`.
- **Password page does not appear:** confirm `APP_PASSWORD` is entered in the
  Streamlit Secrets field and reboot the app.
- **Saved template disappeared:** load its downloaded JSON scenario again; hosted
  filesystem persistence is not guaranteed.
