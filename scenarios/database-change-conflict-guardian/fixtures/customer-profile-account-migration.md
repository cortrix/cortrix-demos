# Customer profile account migration

Customer Profiles moved `profile.account_id` into a nested ownership record. The change belongs to the profile store and has no effect on the PostgreSQL `orders` table.
