# Financial rules

Amounts are parsed from strict decimal strings into integer cents. Floats, exponents, negative input amounts, excessive precision, zero posted amounts, and amounts above AUD 1,000,000,000 are rejected. Zero custom shares are allowed. Signed ledger storage encodes direction, not negative user-input money.

For canonical relationship endpoints L/R, a positive entry means R owes L; a negative entry means L owes R. L sees sum(cents); R sees its negative. Only endpoints contribute to that user's home balance. An administrator's third-party ledgers do not inflate their own net position. No editable balance field exists.

| Action from A's perspective | Effect |
|---|---|
| Money given | B owes A more |
| Money taken | A owes B more |
| Repayment received | B owes A less |
| Repayment made | A owes B less |
| Reversal | Exact opposite of the referenced entry; original preserved |
| Adjustment | Explicit creditor, positive amount and mandatory reason; audited |

Repayment validation and posting share a relationship row lock. The payment must match the direction of outstanding debt and must not overpay it. Date, note, optional receipt and optional same-ledger source-entry reference are retained. Third-party local payments require choosing the participant perspective explicitly.

## Splits

Equal allocation sorts participant IDs, computes quotient/remainder with `divmod`, and allocates one cent to each of the first remainder participants. Thus 10,000 cents across three people is 3,334 + 3,333 + 3,333. Custom shares must have exactly the selected participant keys, all nonnegative integer cents, and sum to the total. Payer need not be a participant; subset splits are supported.

Each non-payer share becomes a debt to the actual payer. No self-obligation is generated. A third-party payer never gets replaced with the current user. The bill, shares, and obligations are committed together. A bill source ID ties every generated entry back to the bill. Accepted account aliases prevent posting the same person as two participants.

## Groups

For each member: net = amount paid − amount allocated. The sum of all nets is zero. Positive values are creditors; negative values are debtors. Deterministic sorted debtor/creditor matching transfers the smaller remaining amount until all nets are zero. It uses at most creditors + debtors − 1 transfers, but is not claimed to solve the minimum-transfer optimization problem.

Open/review expenses have no ledger effect. Reviewing shows all shares via bill detail, contribution totals, net positions and transfers. Finalization locks the group, checks status/revision/confirmation/disputes/membership/share totals, stores an immutable snapshot, creates every transfer's ledger obligation and notification, and freezes the group in one transaction. Retrying returns the existing snapshot. Finalization records obligations, never payments.

Corrections to open group expenses create a replacement expense and preserve the original shares. Finalized group corrections occur only through ledger reversals or adjustments. The original settlement remains inspectable. Disputes never remove an entry or change its mathematical contribution.
