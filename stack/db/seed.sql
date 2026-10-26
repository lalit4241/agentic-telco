-- Customers mirror Account names in LalitC's Salesforce Dev org (Account read via standard REST in scripts/verify_org.py).
insert into sor.party values
 ('P-1001','Arthur Bennett','arthur.bennett@example.com','{"marketing":{"granted":true,"channel":"digital","capturedAt":"2026-03-02"}}'),
 ('P-1002','David Okafor','david.okafor@example.com','{"marketing":{"granted":true,"channel":"digital","capturedAt":"2026-01-17"}}'),
 ('P-1003','Priya Shah','priya.shah@example.com','{"marketing":{"granted":true,"channel":"verbal","capturedAt":"2025-11-09"}}'),
 ('P-1004','Sarah Mitchell','sarah.mitchell@example.com','{"marketing":{"granted":true,"channel":"digital","capturedAt":"2026-05-21"}}')
on conflict do nothing;
insert into sor.customer values
 ('C-1001','P-1001','Arthur Bennett','Active','{"line":"14 Elm Row","city":"Leeds","postcode":"LS6 2AB","exchange":"LEEDS-HEADINGLEY","technology":["FTTP","FTTC"]}','Arthur Bennett'),
 ('C-1002','P-1002','David Okafor','Active','{"line":"3 Canal Wharf","city":"Manchester","postcode":"M4 7HR","exchange":"MAN-ANCOATS","technology":["FTTP","FTTC"]}','David Okafor'),
 ('C-1003','P-1003','Priya Shah','Active','{"line":"88 Queens Rd","city":"Bristol","postcode":"BS8 1QU","exchange":"BRS-CLIFTON","technology":["FTTP","FTTC"]}','Priya Shah'),
 ('C-1004','P-1004','Sarah Mitchell','Active','{"line":"21 Mill Lane","city":"York","postcode":"YO1 9TX","exchange":"YORK-CENTRAL","technology":["FTTP","FTTC"]}','Sarah Mitchell')
on conflict do nothing;
insert into sor.product_offering values
 ('PO-FIB-150','Fibre 150','Superfast fibre broadband, 150 Mb/s',29,150,'{FTTC,FTTP}','Launched','{}'),
 ('PO-FIB-500','Fibre 500','Ultrafast full fibre, 500 Mb/s',39,500,'{FTTP}','Launched','{}'),
 ('PO-FF-900','Full Fibre 900','Gigabit-class full fibre, 900 Mb/s, Wi-Fi 7 hub',49,900,'{FTTP}','Launched','{}'),
 ('PO-FF-1600','Full Fibre 1.6G','Multi-gig full fibre, 1.6 Gb/s',65,1600,'{XGS-PON}','Launched','{}')
on conflict do nothing;
insert into sor.product_inventory values
 ('PI-1001','C-1001','PO-FIB-150','active',now()),('PI-1002','C-1002','PO-FIB-150','active',now()),
 ('PI-1003','C-1003','PO-FIB-150','active',now()),('PI-1004','C-1004','PO-FIB-150','active',now())
on conflict do nothing;
insert into oss.capacity values ('LEEDS-HEADINGLEY',480,312,0.65),('MAN-ANCOATS',512,380,0.74),('BRS-CLIFTON',256,170,0.66),('YORK-CENTRAL',384,221,0.58)
on conflict do nothing;
insert into l3.credit_score values ('C-1001',598,'Bureau-X (synthetic)','2026-10-01'),('C-1002',712,'Bureau-X (synthetic)','2026-10-01'),
 ('C-1003',688,'Bureau-X (synthetic)','2026-10-01'),('C-1004',761,'Bureau-X (synthetic)','2026-10-01') on conflict do nothing;
insert into l3.usage values ('C-1001',940,148,14,true),('C-1002',610,139,9,true),('C-1003',420,96,6,false),('C-1004',780,145,11,true) on conflict do nothing;
