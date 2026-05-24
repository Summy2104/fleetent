## MODIFIED Requirements

### Requirement: Look up user by platform identity
The user_store module SHALL provide a function to look up or create an internal user by platform identity.

#### Scenario: Existing platform user
- **WHEN** `user_store.get_or_create_im_user("slack", "U123")` is called and a matching row exists in `im_users`
- **THEN** the function returns the associated internal `User` object without creating new rows

#### Scenario: New platform user
- **WHEN** `user_store.get_or_create_im_user("slack", "U999")` is called and no matching row exists
- **THEN** a new `User` is created in `users`, a new row is inserted in `im_users`, and the `User` is returned
