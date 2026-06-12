# OpenSanctions Dataset Catalogue

**Index URL:** `https://data.opensanctions.org/datasets/latest/index.json`  
**Per-dataset metadata:** `https://data.opensanctions.org/datasets/latest/{name}/index.json`  
**Download URL pattern:** `https://data.opensanctions.org/datasets/latest/{name}/entities.ftm.json`  
**Last verified:** 2026-06-03

---

## Collections (aggregated meta-datasets)

These combine many sources and are the best choice for broad screening. They are large.

| Name | Title | Description | Approx Size |
|---|---|---|---|
| `default` | OpenSanctions Default | Quality-filtered data for screening & investigative use; best all-purpose dataset | ~400 MB |
| `sanctions` | Consolidated Sanctions | All sanctions sources globally (70+ lists) | ~500 MB |
| `crime` | Warrants & Criminal Entities | Criminal activity datasets (60+ sources) | ~300 MB |
| `debarment` | Debarred Companies & Individuals | Procurement exclusions (50+ jurisdictions) | ~200 MB |
| `peps` | Politically Exposed Persons | PEP datasets globally | ~300 MB |
| `maritime` | Maritime-Related Sanctions | Shipping/vessel focused | ~50 MB |
| `enforcement` | Enforcement Actions | Regulatory notices and penalties | ~100 MB |
| `wanted` | Wanted Lists | Law enforcement wanted persons | ~50 MB |
| `special_interest` | Special Interest Watchlists | Various watchlists | ~100 MB |
| `regulatory` | Regulatory Watchlists | Financial regulatory lists | ~100 MB |
| `securities` | Sanctioned Securities | Companies with LEI/ISIN codes | ~200 MB |

---

## Crypto / Blockchain Datasets

| Name | Title | Summary | Entity Count |
|---|---|---|---|
| `il_mod_crypto` | Israel Sanctioned Crypto Wallets | Crypto wallets seized by Israeli MoD via Administrative Seizure Orders. Best source for crypto wallet screening on sanctions. | 4,202 entities |
| `us_fbi_lazarus_crypto` | US FBI Lazarus Group Crypto Wallets | Crypto addresses connected to $41M Stake.com theft attributed to North Korea's Lazarus Group | Small |
| `ransomwhere` | Ransomwhere Ransomware Addresses | Cryptocurrency addresses linked to ransomware payment attacks (community-maintained) | Thousands |

**For crypto wallet screening:** Start with all three above (small, fast). Then widen to `sanctions` collection if no hits.

---

## US / OFAC Sanctions

| Name | Title | Summary |
|---|---|---|
| `us_ofac_sdn` | OFAC Specially Designated Nationals | Primary US sanctions list — 19,748 targets, 70,592 entities. **Start here for US sanctions.** |
| `us_ofac_cons` | OFAC Consolidated Non-SDN List | Non-SDN OFAC programs (SSI, CAPTA, etc.) |
| `us_ofac_enforcement_actions` | OFAC Enforcement Actions | Civil penalties and enforcement settlements |
| `us_cuba_sanctions` | OFAC Cuba Sanctions | Cuba-specific SDN designations |
| `us_fincen_enforcement` | FinCEN Enforcement Actions | FinCEN civil money penalties |
| `us_fincen_special_measures` | FinCEN Special Measures | High-risk jurisdiction designations (Section 311) |
| `us_fbi_lazarus_crypto` | FBI Lazarus Crypto | See crypto section above |

---

## UN Sanctions

| Name | Title | Summary |
|---|---|---|
| `un_sc_sanctions` | UN Security Council Consolidated | Foundation list that most national lists derive from |
| `un_1718_vessels` | UN SC 1718 Designated Vessels | North Korea-related vessel sanctions |

---

## EU Sanctions

| Name | Title | Summary |
|---|---|---|
| `eu_fsf` | EU Financial Sanctions Files | Main EU consolidated sanctions list |
| `eu_journal_sanctions` | EU Council Official Journal | Russia/Ukraine-focused EU Council designations |
| `eu_travel_bans` | EU Travel Bans | EU consolidated travel restriction list |
| `eu_esma_sanctions` | EU ESMA Sanctions | Financial market regulatory sanctions |

---

## National Sanctions Lists (selected)

| Name | Country | Title |
|---|---|---|
| `gb_hmt_sanctions` | UK | HM Treasury Financial Sanctions |
| `ca_osfi_sanctions` | Canada | OSFI Consolidated Sanctions |
| `au_dfat_sanctions` | Australia | DFAT Consolidated Sanctions |
| `ch_seco_sanctions` | Switzerland | SECO Consolidated Sanctions |
| `jp_mof_sanctions` | Japan | Ministry of Finance Sanctions |
| `sg_mas_sanctions` | Singapore | MAS Sanctions |
| `ua_sfms_blacklist` | Ukraine | SFMS Financial Monitoring Blacklist |
| `ru_nsd_isin` | Russia | NSD ISIN securities (informational) |
| `kp_nsd_reports` | North Korea | DPRK-related sanctions data |
| `ir_treasury_sanctions` | Iran | Iranian Treasury sanctions |

*Full list of 50+ national lists available at `https://data.opensanctions.org/datasets/latest/index.json`*

---

## Development Banks / Multilateral

| Name | Title |
|---|---|
| `adb_sanctions` | Asian Development Bank Sanctions |
| `afdb_sanctions` | African Development Bank Sanctions |
| `iadb_sanctions` | Inter-American Development Bank Debarment |
| `wbg_sanctions` | World Bank Group Sanctions |

---

## Specialised / External

| Name | Title | Notes |
|---|---|---|
| `ext_icij_offshoreleaks` | ICIJ Offshore Leaks | Panama Papers, Pandora Papers, etc. |
| `ext_gleif` | GLEIF Legal Entity Identifier | LEI reference data (non-sanctions) |
| `ann_graph_topics` | Graph-based entity tagging | Auto-generated risk tagging |

---

## Download URL Examples

```
# Crypto wallet datasets (small, fast)
https://data.opensanctions.org/datasets/latest/il_mod_crypto/entities.ftm.json
https://data.opensanctions.org/datasets/latest/us_fbi_lazarus_crypto/entities.ftm.json
https://data.opensanctions.org/datasets/latest/ransomwhere/entities.ftm.json

# US OFAC SDN
https://data.opensanctions.org/datasets/latest/us_ofac_sdn/entities.ftm.json

# Broad sanctions collection
https://data.opensanctions.org/datasets/latest/sanctions/entities.ftm.json

# Per-dataset metadata (size, resource list)
https://data.opensanctions.org/datasets/latest/us_ofac_sdn/index.json
```

---

## Other Available File Formats Per Dataset

Each dataset also offers:
- `targets.nested.json` — one JSON object per target with related entities nested inside
- `targets.simple.csv` — simplified CSV, best for spreadsheet analysis
- `names.txt` — names-only plain text, useful for simple text search
- `senzing.json` — Senzing entity resolution format
- `source.xml` — original source XML (where applicable)
