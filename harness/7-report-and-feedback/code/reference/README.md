# Approved reporting reference

`approved-reference.html` is the user-approved visual and structural baseline.
It is tracked through version-control history and does not require a checksum.

`reference-campaign-builder.py` is retained only to audit how that specific GLM
artifact was produced. It contains campaign-specific paths and assumptions and
must not be used as the generic renderer.

Do not overwrite the approved reference in place. A future replacement requires
explicit approval and an explanation committed with the change.
