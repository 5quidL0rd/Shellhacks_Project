// Knowledge graph schema. Applied by kg/load.py; safe to run repeatedly.
//
// Nodes
//   (:Company {ticker, name, cik, in_universe})
//       ticker is the key; companies outside the universe use a name slug.
//   (:Sector  {name})
//   (:Country {name})
//
// Relationships (every edge carries source, filing_url, evidence, confidence)
//   (:Company)-[:SUPPLIES]->(:Company)       supplier -> customer
//   (:Company)-[:COMPETES_WITH]->(:Company)  stored once; query without direction
//   (:Company)-[:IN_SECTOR]->(:Sector)
//   (:Company)-[:OPERATES_IN {kind}]->(:Country)
//       kind: headquarters | manufacturing | major_market

CREATE CONSTRAINT company_ticker IF NOT EXISTS FOR (c:Company) REQUIRE c.ticker IS UNIQUE;
CREATE CONSTRAINT sector_name IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT country_name IF NOT EXISTS FOR (c:Country) REQUIRE c.name IS UNIQUE;
