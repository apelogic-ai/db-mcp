# Chinook Music Store — Domain Model

## Overview

Chinook represents a digital music store (similar to iTunes). It tracks a catalog of music tracks organized by artists, albums, and genres, along with customer purchases (invoices) and employee data.

## Core Entities

### Catalog (What's for sale)

- **Artist** — Musicians and bands. Top-level catalog entity.
- **Album** — A collection of tracks by one artist. An artist can have many albums.
- **Track** — Individual songs or media items. The central entity. Each track belongs to one album, one genre, and one media type.
- **Genre** — Music classification (Rock, Jazz, Latin, etc.). 25 genres total.
- **MediaType** — File format (MPEG, AAC, Protected AAC, video). 5 types.
- **Playlist** — Named groupings of tracks (many-to-many via PlaylistTrack).

### Sales (Who bought what)

- **Customer** — Buyers with contact/address info. Each assigned a support rep.
- **Invoice** — A purchase event. One customer per invoice, with date and billing address.
- **InvoiceLine** — Line items on an invoice. Each line = one track purchase with price and quantity.

### Organization (Who works here)

- **Employee** — Staff with a self-referential reporting hierarchy (ReportsTo). Some employees are "Sales Support Agents" assigned to customers.

## Key Relationships

```
Artist 1──* Album 1──* Track *──1 Genre
                         │ *──1 MediaType
                         │
                    PlaylistTrack *──1 Playlist
                         │
                    InvoiceLine *──1 Invoice *──1 Customer *──1 Employee
                                                                  │
                                                              ReportsTo (self)
```

- Artist → Album: one-to-many
- Album → Track: one-to-many
- Track → Genre: many-to-one
- Track → MediaType: many-to-one
- Track ↔ Playlist: many-to-many (via PlaylistTrack)
- Customer → Invoice: one-to-many
- Invoice → InvoiceLine: one-to-many
- InvoiceLine → Track: many-to-one
- Customer → Employee (SupportRepId): many-to-one
- Employee → Employee (ReportsTo): self-referential hierarchy

## Revenue Calculation

Revenue is calculated from **InvoiceLine**, not Invoice.Total:
- **Line revenue** = `InvoiceLine.UnitPrice * InvoiceLine.Quantity`
- **Invoice total** = `SUM(line revenue)` for all lines on that invoice
- Invoice.Total is a denormalized convenience column and should match the sum

To attribute revenue to artists, genres, etc., always join through InvoiceLine → Track.

## Key Concepts

- **All prices are in USD** — no currency conversion needed
- **Track duration** is in **milliseconds** — divide by 1000 for seconds, 60000 for minutes
- **Dates are UTC** — InvoiceDate, BirthDate, HireDate
- **No soft deletes** — if a row is gone, it's gone
- **Billing address on Invoice** is a snapshot at purchase time, may differ from Customer's current address
