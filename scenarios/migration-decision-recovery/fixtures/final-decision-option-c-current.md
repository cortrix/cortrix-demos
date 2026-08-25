# Final migration decision

Status: current and approved. Option B was rejected because cross-region replay tests produced out-of-order writes and checksum divergence after a retry boundary. The final decision is option C: dual write with verified replay before cutover. The decision preserves a nondestructive cutover, requires checksum parity, and retains a 30-minute rollback window. This is the current migration authority.
