# Install, update and rollback

Use a versioned GitHub Release asset, not a moving branch archive. Verify the asset against the release `SHA256SUMS.txt`, extract it, then run `scripts/install.py --target <skills-dir>`. The installer is offline and executes `doctor` on the installed copy.

Before an update, back up the SQLite database and record the current Release tag and asset digest. Install the new Skill into a staging directory, run `doctor --db <copy-of-db>`, migrate the copy, and run the acceptance suite. Only then replace the installed Skill and migrate the real database.

Code rollback means reinstalling the prior immutable Release asset. Data rollback means restoring the pre-migration backup. Never point an older binary at a database whose schema is newer than it supports.

