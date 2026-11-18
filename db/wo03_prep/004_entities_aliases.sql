-- CAT-WO-03 ruling (a), Ryan 2026-11-17: 11 new entities + Datum-code aliases. Branch only until the release migration.
-- CIP-II (GP) is a NEW GP entity; it is NOT CIP2A (CIP2A = the CIP-II Admin manco).
-- Each new entity code also needs label choices: labels_setup.py --sync-choices (release step, not prep).
INSERT INTO ref.entity (entity_code, name, entity_type, family, active, provisional, notes) VALUES
  ('MTV-III (PF)',      'MTV-III (PF)',      'fund', 'MTV',  true, false, 'CAT-WO-03 (a) 2026-11-17; Datum MTV-III (PF)'),
  ('MTV-III (PF) (GP)', 'MTV-III (PF) (GP)', 'gp',   'MTV',  true, false, 'CAT-WO-03 (a) 2026-11-17; Datum MTV-III (PF) (GP)'),
  ('ASOF (GP)',         'ASOF (GP)',         'gp',   'ASOF', true, false, 'CAT-WO-03 (a) 2026-11-17; Datum ASOF (GP)'),
  ('X (GP)',            'X (GP)',            'gp',   'X',    true, false, 'CAT-WO-03 (a) 2026-11-17; Datum Allegis X (GP)'),
  ('CIP-II (GP)',       'CIP-II (GP)',       'gp',   'CIP',  true, false, 'CAT-WO-03 (a) 2026-11-17; Datum CIP-II (GP); NOT CIP2A (CIP-II Admin manco)'),
  ('NL-I (GP)',         'NL-I (GP)',         'gp',   'NL',   true, false, 'CAT-WO-03 (a) 2026-11-17; Datum NL-I (GP)'),
  ('NL-II (GP)',        'NL-II (GP)',        'gp',   'NL',   true, false, 'CAT-WO-03 (a) 2026-11-17; Datum NL-II (GP)'),
  ('FUNDAM',            'FUNDAM',            'spv',  NULL,   true, false, 'CAT-WO-03 (a) 2026-11-17; Datum Fundam (SPV)'),
  ('LS-I',              'LS-I',              'spv',  NULL,   true, false, 'CAT-WO-03 (a) 2026-11-17; Datum Lightship I (SPV)'),
  ('LS-II',             'LS-II',             'spv',  NULL,   true, false, 'CAT-WO-03 (a) 2026-11-17; Datum Lightship II (SPV)'),
  ('ATTOTUDE',          'ATTOTUDE',          'spv',  NULL,   true, false, 'CAT-WO-03 (a) 2026-11-17; Datum Attotude (SPV)')
ON CONFLICT (entity_code) DO UPDATE SET entity_type = EXCLUDED.entity_type, family = EXCLUDED.family,
  provisional = false, notes = EXCLUDED.notes;

-- Datum company code -> catalog entity (only where the codes differ; identical codes map exactly).
INSERT INTO ref.entity_alias (alias, entity_code, source, generic) VALUES
  ('Allegis X',          'X',        'datum cat-wo-03 2026-11-17', false),
  ('Dragos (SPV)',       'ACCSO',    'datum cat-wo-03 2026-11-17', false),
  ('Shape MTV-VI (SPV)', 'MTV-VI',   'datum cat-wo-03 2026-11-17', false),
  ('Allegis IVY (SPV)',  'IVY',      'datum cat-wo-03 2026-11-17', false),
  ('Allegis TM (SPV)',   'TM',       'datum cat-wo-03 2026-11-17', false),
  ('Allegis X (GP)',     'X (GP)',   'datum cat-wo-03 2026-11-17', false),
  ('Fundam (SPV)',       'FUNDAM',   'datum cat-wo-03 2026-11-17', false),
  ('Lightship I (SPV)',  'LS-I',     'datum cat-wo-03 2026-11-17', false),
  ('Lightship II (SPV)', 'LS-II',    'datum cat-wo-03 2026-11-17', false),
  ('Attotude (SPV)',     'ATTOTUDE', 'datum cat-wo-03 2026-11-17', false)
ON CONFLICT DO NOTHING;

-- PROPOSED (awaiting Ryan's ruling; NOT applied): types for the 6 untyped entities.
--   X        -> fund  (Datum company_kind = fund)
--   NL-I     -> fund  (Datum company_kind = fund)
--   NL-II    -> fund  (Datum company_kind = fund)
--   TM       -> spv   (Datum: Allegis TM (SPV))
--   XI       -> fund  (successor fund in the X family; no Datum roster yet)
--   CYBER-II -> fund  (family CYBER is unset; ACCSO, the CYBER-family SPV, is spv - confirm CYBER-II is the fund, not an SPV)
-- UPDATE ref.entity SET entity_type = 'fund' WHERE entity_code IN ('X', 'NL-I', 'NL-II', 'XI', 'CYBER-II') AND entity_type IS NULL;
-- UPDATE ref.entity SET entity_type = 'spv'  WHERE entity_code = 'TM' AND entity_type IS NULL;
