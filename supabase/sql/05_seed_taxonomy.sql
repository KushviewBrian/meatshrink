-- 5) Seed categories into app_enums('category')

insert into app_enums(namespace, value) values
('category','Beef'), ('category','Pork'), ('category','Poultry'), ('category','Lamb/Goat'),
('category','Veal'), ('category','Seafood'), ('category','Deli/Smoked'), ('category','Value-Added')
on conflict do nothing;
