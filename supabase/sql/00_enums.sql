-- 0) Enumerations via CHECK-table (no ENUMs for evolvability)

create table if not exists app_enums (
  namespace text not null,
  value     text not null,
  primary key (namespace, value)
);

insert into app_enums(namespace, value) values
('role','associate'), ('role','lead'), ('role','manager'), ('role','auditor'), ('role','admin'),
('event_type','Spoilage'),('event_type','Trim/Waste'),('event_type','Theft'),('event_type','Damage'),
('event_type','Markdown'),('event_type','Rework'),('event_type','Return'),
('product_type','Raw'),('product_type','Ground'),('product_type','Marinated'),
('product_type','Value-Added'),('product_type','Ready-to-Cook'),('product_type','Ready-to-Eat')
on conflict do nothing;
