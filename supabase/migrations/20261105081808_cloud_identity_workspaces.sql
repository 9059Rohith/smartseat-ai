create schema if not exists smartseat_private;
revoke all on schema smartseat_private from public, anon;
grant usage on schema smartseat_private to authenticated;

create table public.smartseat_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '' check (length(display_name)<=100),
  avatar_url text,
  created_at timestamptz not null default now()
);
create table public.smartseat_workspaces (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null unique references auth.users(id) on delete cascade,
  name text not null check (length(btrim(name)) between 1 and 100),
  timezone text not null default 'Asia/Kolkata',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table public.smartseat_memberships (
  workspace_id uuid not null references public.smartseat_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner','manager','staff')),
  created_at timestamptz not null default now(),
  primary key(workspace_id,user_id)
);
create index smartseat_membership_user on public.smartseat_memberships(user_id,workspace_id);

create function smartseat_private.is_member(target uuid) returns boolean language sql stable security definer set search_path=''
as $$select auth.uid() is not null and exists(select 1 from public.smartseat_memberships where workspace_id=target and user_id=auth.uid())$$;
create function smartseat_private.is_owner(target uuid) returns boolean language sql stable security definer set search_path=''
as $$select auth.uid() is not null and exists(select 1 from public.smartseat_workspaces where id=target and owner_id=auth.uid())$$;
create function smartseat_private.is_operator(target uuid) returns boolean language sql stable security definer set search_path=''
as $$select auth.uid() is not null and exists(select 1 from public.smartseat_memberships where workspace_id=target and user_id=auth.uid() and role in ('owner','manager'))$$;
revoke all on all functions in schema smartseat_private from public,anon;
grant execute on function smartseat_private.is_member(uuid),smartseat_private.is_owner(uuid),smartseat_private.is_operator(uuid) to authenticated;

alter table public.smartseat_profiles enable row level security;
alter table public.smartseat_workspaces enable row level security;
alter table public.smartseat_memberships enable row level security;
revoke all on public.smartseat_profiles,public.smartseat_workspaces,public.smartseat_memberships from anon;
grant select,insert,update on public.smartseat_profiles to authenticated;
grant select,update on public.smartseat_workspaces to authenticated;
grant select on public.smartseat_memberships to authenticated;
create policy profile_read on public.smartseat_profiles for select to authenticated using(user_id=(select auth.uid()));
create policy profile_insert on public.smartseat_profiles for insert to authenticated with check(user_id=(select auth.uid()));
create policy profile_update on public.smartseat_profiles for update to authenticated using(user_id=(select auth.uid())) with check(user_id=(select auth.uid()));
create policy workspace_read on public.smartseat_workspaces for select to authenticated using(smartseat_private.is_member(id));
create policy workspace_update on public.smartseat_workspaces for update to authenticated using(smartseat_private.is_owner(id)) with check(owner_id=(select auth.uid()));
create policy membership_read on public.smartseat_memberships for select to authenticated using(smartseat_private.is_member(workspace_id));

create table public.smartseat_floor_cache (
  workspace_id uuid primary key references public.smartseat_workspaces(id) on delete cascade,
  payload jsonb not null check(octet_length(payload::text)<2097152),
  source_at timestamptz not null,
  updated_at timestamptz not null default now()
);
create table public.smartseat_report_cache (
  workspace_id uuid not null references public.smartseat_workspaces(id) on delete cascade,
  period text not null check(period in ('today','yesterday','week','thisweek','lastweek','weekend','month','custom')),
  payload jsonb not null check(octet_length(payload::text)<2097152),
  source_at timestamptz not null,
  updated_at timestamptz not null default now(),
  primary key(workspace_id,period)
);
create table public.smartseat_daily_metrics (
  workspace_id uuid not null references public.smartseat_workspaces(id) on delete cascade,
  period text not null,
  day date not null,
  visits integer not null default 0 check(visits>=0),
  known_guests integer not null default 0 check(known_guests>=0),
  occupancy numeric not null default 0 check(occupancy between 0 and 100),
  turnover integer not null default 0 check(turnover>=0),
  confirmed_cleanings integer not null default 0 check(confirmed_cleanings>=0),
  source_at timestamptz not null,
  primary key(workspace_id,period,day)
);
create table public.smartseat_audit_events (
  id bigint generated always as identity primary key,
  workspace_id uuid references public.smartseat_workspaces(id) on delete cascade,
  actor_id uuid not null references auth.users(id) on delete cascade,
  event text not null check(event in ('signed_in','signed_out','password_reset_requested','engine_connected','workspace_created','workspace_updated','profile_updated')),
  created_at timestamptz not null default now()
);
create index smartseat_audit_workspace_time on public.smartseat_audit_events(workspace_id,created_at desc);
alter table public.smartseat_floor_cache enable row level security;
alter table public.smartseat_report_cache enable row level security;
alter table public.smartseat_daily_metrics enable row level security;
alter table public.smartseat_audit_events enable row level security;
revoke all on public.smartseat_floor_cache,public.smartseat_report_cache,public.smartseat_daily_metrics,public.smartseat_audit_events from anon;
grant select,insert,update on public.smartseat_floor_cache,public.smartseat_report_cache,public.smartseat_daily_metrics to authenticated;
grant select on public.smartseat_audit_events to authenticated;
create policy floor_read on public.smartseat_floor_cache for select to authenticated using(smartseat_private.is_member(workspace_id));
create policy floor_insert on public.smartseat_floor_cache for insert to authenticated with check(smartseat_private.is_operator(workspace_id));
create policy floor_update on public.smartseat_floor_cache for update to authenticated using(smartseat_private.is_operator(workspace_id)) with check(smartseat_private.is_operator(workspace_id));
create policy report_read on public.smartseat_report_cache for select to authenticated using(smartseat_private.is_member(workspace_id));
create policy report_insert on public.smartseat_report_cache for insert to authenticated with check(smartseat_private.is_operator(workspace_id));
create policy report_update on public.smartseat_report_cache for update to authenticated using(smartseat_private.is_operator(workspace_id)) with check(smartseat_private.is_operator(workspace_id));
create policy daily_read on public.smartseat_daily_metrics for select to authenticated using(smartseat_private.is_member(workspace_id));
create policy daily_insert on public.smartseat_daily_metrics for insert to authenticated with check(smartseat_private.is_operator(workspace_id));
create policy daily_update on public.smartseat_daily_metrics for update to authenticated using(smartseat_private.is_operator(workspace_id)) with check(smartseat_private.is_operator(workspace_id));
create policy audit_read on public.smartseat_audit_events for select to authenticated using(actor_id=(select auth.uid()) or (workspace_id is not null and smartseat_private.is_owner(workspace_id)));

create function public.smartseat_create_workspace(workspace_name text) returns uuid language plpgsql security definer set search_path='' as $$
declare current_user_id uuid:=auth.uid(); result uuid;
begin
  if current_user_id is null then raise exception 'Authentication required' using errcode='42501';end if;
  if length(btrim(workspace_name)) not between 1 and 100 then raise exception 'Invalid restaurant name';end if;
  perform pg_advisory_xact_lock(hashtextextended(current_user_id::text,0));
  select id into result from public.smartseat_workspaces where owner_id=current_user_id;
  if result is null then
    insert into public.smartseat_workspaces(owner_id,name) values(current_user_id,btrim(workspace_name)) returning id into result;
    insert into public.smartseat_memberships(workspace_id,user_id,role) values(result,current_user_id,'owner');
    insert into public.smartseat_audit_events(workspace_id,actor_id,event) values(result,current_user_id,'workspace_created');
  end if;
  return result;
end$$;
revoke all on function public.smartseat_create_workspace(text) from public,anon;
grant execute on function public.smartseat_create_workspace(text) to authenticated;

create function public.smartseat_record_event(target uuid,event_name text) returns void language plpgsql security definer set search_path='' as $$
begin
  if auth.uid() is null or (target is not null and not smartseat_private.is_member(target)) then
    raise exception 'Access denied' using errcode='42501';end if;
  if event_name not in ('signed_in','signed_out','password_reset_requested','engine_connected','workspace_updated','profile_updated') then raise exception 'Unsupported event';end if;
  insert into public.smartseat_audit_events(workspace_id,actor_id,event) values(target,auth.uid(),event_name);
end$$;
revoke all on function public.smartseat_record_event(uuid,text) from public,anon;
grant execute on function public.smartseat_record_event(uuid,text) to authenticated;
