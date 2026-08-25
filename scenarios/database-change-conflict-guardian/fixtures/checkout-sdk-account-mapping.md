# Checkout SDK account mapping

The Checkout SDK serializes a client-side `accountId` property before calling its own gateway. Its property name is not a PostgreSQL column name and does not define the active `orders` schema.
