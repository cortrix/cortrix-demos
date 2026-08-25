# Cross-region replay evidence

Three controlled replay trials for option B produced out-of-order writes after the retry boundary. Two trials diverged on 1,284 records and one diverged on 1,317 records. Repeating the trial from a clean snapshot reproduced the failure. Option C dual write with verified replay maintained order and checksum parity in all three trials. This evidence supports rejection of option B.
