# FollowTheMoney (FtM) Schema Reference

OpenSanctions uses the FollowTheMoney (FtM) ontology. Each line in `entities.ftm.json` is a JSON object.

---

## Entity Line Structure

```json
{
  "id": "NK-ABC123",
  "caption": "Display Name",
  "schema": "CryptoWallet",
  "properties": {
    "publicKey": ["0xabc123..."],
    "topics": ["sanction"],
    "name": ["Entity Name"],
    "country": ["us"],
    "program": ["OFAC SDN"]
  },
  "datasets": ["us_ofac_sdn", "il_mod_crypto"],
  "referents": ["related-entity-id"],
  "first_seen": "2024-01-15",
  "last_seen": "2026-06-03",
  "last_change": "2025-11-01"
}
```

---

## Matchable Schema Types (Primary Entities)

| Schema | Count | Use For |
|---|---|---|
| `Person` | 1,163,047 | Natural persons |
| `Security` | 939,656 | Financial securities/assets |
| `Company` | 241,605 | Corporations, trusts, funds |
| `Organization` | 109,117 | Non-ownable incorporated entities |
| `LegalEntity` | 84,635 | Generic legal party (specificity unknown) |
| `CryptoWallet` | 13,688 | Blockchain addresses |
| `Vessel` | 9,895 | Ships and maritime vehicles |
| `Airplane` | 344 | Aircraft |
| `PublicBody` | 182 | State ministries, departments |

---

## Contextual Schema Types (Relationships)

| Schema | Count | Meaning |
|---|---|---|
| `Occupancy` | 904,055 | Person holding a position |
| `Sanction` | 616,529 | Sanctioned status record |
| `Ownership` | 239,534 | Asset ownership relationship |
| `Position` | 174,497 | Role/post within an organisation |
| `Directorship` | 147,630 | Board/leadership relationship |
| `Employment` | — | Employment relationship |
| `Family` | — | Family relationship |
| `Associate` | — | Business associate link |
| `Identification` | — | ID document record |
| `Payment` | — | Payment relationship |
| `Debt` | — | Debt relationship |
| `Membership` | — | Membership in organisation |

---

## Universal Properties (all entities)

```
name, alias, previousName, weakAlias
country, summary, notes, description
sourceUrl, publisher, wikipediaUrl, wikidataId
keywords, topics, address, addressEntity
program, createdAt, modifiedAt, retrievedAt
```

---

## CryptoWallet Properties

| Property | Type | Description |
|---|---|---|
| `publicKey` | identifier (512 chars) | **The wallet address** — primary search field |
| `accountId` | identifier | Platform-specific account ID |
| `managingExchange` | string | Exchange or custodian name |
| `holder` | entity ref → LegalEntity | Owning person/company |
| `balance` | number | Current balance |
| `amount` | number | Transaction amount |
| `currency` | enum | Currency code |
| `amountUsd` | number | USD equivalent |
| `topics` | enum[] | Risk tags (see below) |

**Search tip:** To find a wallet address, search for the `publicKey` value. The full address appears verbatim in the JSON string.

---

## Person Properties

```
firstName, middleName, lastName, fatherName, motherName, nameSuffix, title
birthDate, birthPlace, birthCountry, deathDate
nationality, citizenship, passportNumber, socialSecurityNumber, gender
profession, education, biography
political, religion, ethnicity
```

---

## LegalEntity / Company / Organization Properties

```
abbreviation, email, phone, website
legalForm, incorporationDate, dissolutionDate
registrationNumber, taxNumber, vatCode
jurisdiction, mainCountry, status, sector
leiCode, imoNumber, swiftBic, dunsCode
opencorporatesUrl, icijId
```

---

## `topics` Risk Tag Vocabulary

| Value | Meaning |
|---|---|
| `sanction` | On a formal sanctions list |
| `sanction.linked` | Associate/linked to sanctioned entity |
| `sanction.counter` | Counter-sanctioned (Russia retaliatory lists) |
| `debarment` | Procurement exclusion |
| `debarment.linked` | Linked to debarred entity |
| `crime` | Criminal / law enforcement relevance |
| `crime.fraud` | Fraud-related |
| `crime.cyber` | Cybercrime / hacking |
| `crime.terror` | Terrorism-related |
| `crime.traffick` | Human/drug trafficking |
| `crime.fin` | Financial crime |
| `pep` | Politically Exposed Person |
| `pep.linked` | Family/associate of PEP |
| `wanted` | Wanted by law enforcement |
| `asset` | Asset owned by a sanctioned entity |
| `fin.bank` | Banking/financial institution |
| `reg.action` | Regulatory action subject |

---

## Sanction Entity Properties (contextual)

The `Sanction` schema records why an entity is sanctioned:

```
entity          → link to the sanctioned Person/Company
program         → sanctions program name (e.g. "CYBER2", "RUSSIA-EO14024")
provisions      → specific legal provisions
startDate       → designation date
endDate         → delisting date (if delisted)
reason          → narrative reason for designation
authority       → designating authority name
sourceUrl       → source document URL
```

---

## Property Value Format

All property values are **arrays of strings**, even when only one value exists:

```json
{ "publicKey": ["0xabc123"] }          ✓ correct
{ "publicKey": "0xabc123" }            ✗ never this format
{ "name": ["Alice Smith", "A. Smith"] } ✓ multiple aliases as array
```

Dates follow ISO 8601 with variable precision: `"2024"`, `"2024-03"`, `"2024-03-15"`.

Countries use 2-letter ISO codes or territory codes: `"us"`, `"ru"`, `"kp"`.

---

## FtM JSON Search Patterns

```bash
# Search for a crypto wallet address
rg -F "0xYOUR_ADDRESS" dataset.ftm.json

# Find all CryptoWallet entities
rg '"schema": "CryptoWallet"' dataset.ftm.json

# Find entities with "sanction" topic
rg '"sanction"' dataset.ftm.json | rg '"schema"'

# Find entities from a specific dataset
rg '"us_ofac_sdn"' dataset.ftm.json | head -5

# Count matches
rg -c "TARGET" dataset.ftm.json
```
