# Offline runtime

The container runs fully offline with no network access during agent work or verification.
`allow_internet` is false in task metadata. Solving and verification do not require
internet access, package downloads (`apt`, `pip`, `npm`, `curl`, `wget`), or external APIs.
Use only preinstalled tooling and bundled fixtures under `/app/environment`.
