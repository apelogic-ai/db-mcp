# Schema Gotchas

## Track.Milliseconds — Not Seconds!
- The `Milliseconds` column stores duration in **milliseconds**
- A value of 343719 means ~5.7 minutes, not 343,719 seconds
- Always divide by 1000 for seconds, 60000 for minutes
- Common mistake: displaying raw value as "343719 seconds" (that's 4 days!)

## Employee.ReportsTo — Self-Referential FK
- `Employee.ReportsTo` references `Employee.EmployeeId`
- The General Manager has `ReportsTo = NULL` (top of hierarchy)
- Use recursive CTEs or self-joins to traverse the org chart
- Only 8 employees total, so hierarchy is shallow

## No Soft Deletes
- There are no `deleted_at`, `is_active`, or `status` columns on any table
- If a record doesn't exist, it was never there (or was hard-deleted)
- No need to filter out "inactive" records

## Invoice.Total is Denormalized
- `Invoice.Total` is a convenience column, not the source of truth
- The real revenue is `SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity)`
- They should match, but always prefer InvoiceLine for aggregations
- Using Invoice.Total for per-track/per-genre breakdowns is impossible

## Track.Composer is Often NULL
- Many tracks have no composer listed
- Don't use `Composer` in GROUP BY without handling NULLs
- Use `COALESCE(Composer, 'Unknown')` when displaying

## Track.AlbumId and GenreId are Nullable
- Some tracks may not belong to an album or have a genre
- Use LEFT JOIN instead of INNER JOIN if you need all tracks

## PlaylistTrack Has No Extra Columns
- It's a pure junction table — just `PlaylistId` and `TrackId`
- No ordering column, no added-date — track order in playlists is undefined

## Billing Address vs Customer Address
- Invoice stores billing address as a snapshot at purchase time
- Customer table has current address
- For geographic analysis of purchases, use `Invoice.BillingCountry`
- For current customer location, use `Customer.Country`
