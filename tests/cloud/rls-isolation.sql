begin;
insert into auth.users(id,email) values('11111111-1111-4111-8111-111111111111','rls-one@example.invalid'),('22222222-2222-4222-8222-222222222222','rls-two@example.invalid');
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
select public.smartseat_create_workspace('Isolation test one');
insert into public.smartseat_floor_cache(workspace_id,payload,source_at) select id,'{"tables":[],"cameras":[]}'::jsonb,now() from public.smartseat_workspaces;
do $$begin
 if (select count(*) from public.smartseat_workspaces)<>1 then raise exception 'First account workspace mismatch';end if;
 if (select count(*) from public.smartseat_floor_cache)<>1 then raise exception 'Own floor inaccessible';end if;
end$$;
select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
do $$begin
 if exists(select 1 from public.smartseat_workspaces) then raise exception 'Cross-account workspace leak';end if;
 if exists(select 1 from public.smartseat_floor_cache) then raise exception 'Cross-account floor leak';end if;
 if exists(select 1 from public.smartseat_audit_events) then raise exception 'Cross-account audit leak';end if;
 begin
  insert into public.smartseat_profiles(user_id,display_name) values('11111111-1111-4111-8111-111111111111','Forbidden');
  raise exception 'Cross-account profile write accepted';
 exception when insufficient_privilege then null;end;
end$$;
select public.smartseat_create_workspace('Isolation test two');
do $$begin
 if (select count(*) from public.smartseat_workspaces)<>1 then raise exception 'Second account workspace mismatch';end if;
 if (select count(*) from public.smartseat_memberships)<>1 then raise exception 'Membership leak';end if;
end$$;
set local role anon;
do $$begin
 begin perform * from public.smartseat_floor_cache;raise exception 'Anonymous floor access accepted';exception when insufficient_privilege then null;end;
 begin perform public.smartseat_create_workspace('Forbidden');raise exception 'Anonymous workspace creation accepted';exception when insufficient_privilege then null;end;
end$$;
reset role;
rollback;
select 'PASS: own workspace, cross-account isolation, denied writes, anonymous denial; test records rolled back' as result;
