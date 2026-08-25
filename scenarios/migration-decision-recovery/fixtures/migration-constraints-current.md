# Current migration constraints

The constraints that still apply are: no destructive cutover; checksum parity is required before traffic moves; rollback capability must remain available for 30 minutes; production writes cannot be paused for more than 90 seconds; and all replay gaps must be explainable. These constraints remain current after option B was rejected.
