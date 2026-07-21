# Security and trust boundaries

## PDF permissions

Protected export uses pikepdf/QPDF AES-256 security revision 6. It disables
ordinary modification, annotations, form filling, page assembly, extraction,
and copying by default; printing is independently configurable and accessibility
extraction stays enabled. The completed PDF is reopened with pikepdf and pypdf,
and export fails closed on any encryption or permission mismatch.

PDF permissions are advisory controls honored by compliant applications. They
do not prevent screenshots, photography, password guessing, decryption, or
reconstruction. They are not cryptographic authenticity or a digital signature.

## Secrets

Owner and document-open passwords are function arguments and masked form values,
not model fields. They are absent from scenarios, batch schemas, manifests,
metadata, output names, logs, and retained application state. Batch password
fields are rejected by name before row validation.

## Uploaded images

The application validates decoded format rather than filename extensions,
corrects EXIF orientation, limits original bytes and decoded pixels, strips
metadata, resizes/compresses a processed copy, verifies its hash, and embeds only
that processed copy in portable scenarios. Logos and signature images require
explicit authorization before preview or export.

## Local service

The launcher binds Streamlit only to `127.0.0.1`, disables telemetry and file
watching, selects a free loopback port, and keeps no required external network
dependency. The installer targets a per-user read-only program directory.

## Hosted service

`streamlit_app.py` enables hosted mode and supports an optional `APP_PASSWORD`
from Streamlit Secrets or `COA_APP_PASSWORD` from the server environment. Password
comparison uses a constant-time digest comparison and successful access is stored
only in Streamlit session state. The password must never be committed to source.

This lightweight gate is defense in depth, not identity management, rate limiting,
or audit logging. Sensitive deployments should also use the hosting provider's
private sharing controls. Uploaded files and generated documents remain available
to the running server process while their session is active. Host filesystem state
is not treated as durable storage.

## Reporting issues

Do not include report contents, images, scenarios, passwords, or personal data in
an issue. Provide the application version, dependency/build identifier, a minimal
fictional reproduction, and sanitized diagnostic excerpts.
