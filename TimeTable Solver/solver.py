"""College Timetable Solver — CP-SAT (OR-Tools).
Input : {events, slots, days, resources}  (app ke buildEvents() se aata hai)
Output: {status, placements: {eventId: {di, s, room}}}
"""
import json
from ortools.sat.python import cp_model


def _solve_once(data, time_limit=240, workers=8, seed=0):
    events = data['events']; slots = data['slots']; days = data['days']; resources = data['resources']
    nD = len(days); nS = len(slots)
    roomById = {r['name']: r for r in resources}
    start2h = [i for i in range(nS - 1) if slots[i]['end'] == slots[i + 1]['start']]
    m = cp_model.CpModel()

    def allowed_rooms(e):
        """SIMPLE rules:
        - lectures/tutorials -> classrooms (A201,A202,A204,A206,B204,B205,B206)
        - labs -> lab rooms (A205, B101-B106, LAB-1/2/3)
          EXCEPT: GENERAL dept faculty ki lab (physics) -> classroom
        - fixed room (SP HALL/GROUND) -> wahi
        """
        if e.get('roomFixed'):
            return [e['roomFixed']]
        if e.get('labClassroom'):
            # classroom-lab (jaise M.PHYSICS): dept ke apne classrooms
            dep = (e.get('roomDept') or '').strip().upper()
            oc = [r['name'] for r in resources if not r.get('onlyPinned') and r['type'] == 'classroom' and (r.get('dept') or '').strip().upper() == dep]
            if oc:
                return oc
            return [r['name'] for r in resources if not r.get('onlyPinned') and r['type'] == 'classroom']
        if e['resourceType'] == 'classroom':
            return [r['name'] for r in resources if not r.get('onlyPinned') and r['type'] == 'classroom']
        # LAB/BATCH -> faculty ke dept ke lab rooms; agar us dept ke lab rooms hi
        # nahi (subject dept fallback bhi na mile) -> koi bhi lab room
        dep = (e.get('roomDept') or '').strip().upper()
        own = [r['name'] for r in resources if not r.get('onlyPinned') and r['type'] == 'lab' and (r.get('dept') or '').strip().upper() == dep]
        if own:
            return own
        return [r['name'] for r in resources if not r.get('onlyPinned') and r['type'] == 'lab']

    winIds = {}
    for e in events:
        w = e.get('windowId')
        if w is not None:
            winIds.setdefault(w, []).append(e)
    winVars = {}
    for w, es in winIds.items():
        dW = m.NewIntVar(0, nD - 1, 'dw_' + w); sW = m.NewIntVar(0, nS - 1, 'sw_' + w)
        if es[0]['duration'] > 1:
            m.AddAllowedAssignments([sW], [[s] for s in start2h])
        winVars[w] = (dW, sW)

    evD = {}; evS = {}; evRooms = {}
    for e in events:
        eid = e['id']; w = e.get('windowId')
        if w is not None:
            evD[eid], evS[eid] = winVars[w]
        else:
            evD[eid] = m.NewIntVar(0, nD - 1, 'd_' + eid)
            sv = m.NewIntVar(0, nS - 1, 's_' + eid)
            if e['duration'] > 1:
                m.AddAllowedAssignments([sv], [[s] for s in start2h])
            evS[eid] = sv
        rooms = allowed_rooms(e)
        if not rooms:
            return {'status': 'ERROR', 'error': 'NO_ROOM: ' + e.get('label', eid)}
        evRooms[eid] = rooms
    # TUTORIAL: same tutorial ke batches EK HI room me — aur room ki capacity
    # batches ke barabar ya zyada (warna capacity tootegi). Room list bhi
    # same kar do (rvars se PEHLE).
    for w, es in winIds.items():
        if not str(w).startswith('TW'):
            continue
        common = None
        for e in es:
            common = set(evRooms[e['id']]) if common is None else (common & set(evRooms[e['id']]))
        if not common:
            continue
        shared = sorted([r for r in common if max(1, (roomById.get(r, {}).get('capacity') or 1)) >= len(es)])
        if not shared:
            shared = sorted(common)
        for e in es:
            evRooms[e['id']] = shared
    rvars = {}
    for e in events:
        eid = e['id']
        rvars[eid] = m.NewIntVar(0, max(0, len(evRooms[eid]) - 1), 'r_' + eid)

    cover = {}
    for e in events:
        eid = e['id']; dur = e['duration']
        for di in range(nD):
            dayIs = m.NewBoolVar('day_%s_%d' % (eid, di))
            m.Add(evD[eid] == di).OnlyEnforceIf(dayIs)
            m.Add(evD[eid] != di).OnlyEnforceIf(dayIs.Not())
            for si in range(nS):
                slotCov = m.NewBoolVar('sl_%s_%d' % (eid, si))
                m.AddElement(evS[eid], [1 if (s <= si < s + dur) else 0 for s in range(nS)], slotCov)
                cv = m.NewBoolVar('c_%s_%d_%d' % (eid, di, si))
                m.AddBoolAnd([dayIs, slotCov]).OnlyEnforceIf(cv)
                m.AddBoolOr([dayIs.Not(), slotCov.Not()]).OnlyEnforceIf(cv.Not())
                cover[(eid, di, si)] = cv

    facEvents = {}
    for e in events:
        for f in e['faculties']:
            facEvents.setdefault(f, []).append(e['id'])
    for f, ids in facEvents.items():
        for di in range(nD):
            for si in range(nS):
                m.Add(sum(cover[(i, di, si)] for i in ids) <= 1)

    # BLOCKED faculty slots (semester-wise solve): in (di,si) par is faculty ki
    # koi class nahi — kyunki wo slot dusre semester me already busy hai
    for f, blk in (data.get('blockFac') or {}).items():
        ids = facEvents.get(f)
        if not ids:
            continue
        for pair in blk:
            di, si = int(pair[0]), int(pair[1])
            if 0 <= di < nD and 0 <= si < nS:
                m.Add(sum(cover[(i, di, si)] for i in ids) == 0)

    batchEvents = {}
    for e in events:
        for g in e['participants']:
            batchEvents.setdefault(g, []).append(e['id'])
    occ = {}
    for g, ids in batchEvents.items():
        for di in range(nD):
            for si in range(nS):
                s = sum(cover[(i, di, si)] for i in ids)
                m.Add(s <= 1)
                occ[(g, di, si)] = s

    for g in batchEvents:
        for di in range(nD):
            for a in range(nS):
                for c in range(a + 2, nS):
                    for mid in range(a + 1, c):
                        m.Add(occ[(g, di, mid)] >= occ[(g, di, a)] + occ[(g, di, c)] - 1)
    for g in batchEvents:
        for di in range(nD):
            for si in range(1, nS):
                m.Add(occ[(g, di, 0)] >= occ[(g, di, si)])

    load = {}
    for e in events:
        for g in e['participants']:
            load[g] = load.get(g, 0) + e['duration']
    minEnd = [i for i in range(nS) if slots[i]['start'] < 15 * 60]
    for g in batchEvents:
        if load.get(g, 0) <= nD * len(minEnd):
            continue
        for di in range(nD):
            for si in minEnd:
                m.Add(occ[(g, di, si)] == 1)

    # PINNED events (Edit feature): fixed day/slot
    for e in events:
        eid = e['id']
        if e.get('fixedDi') is not None:
            m.Add(evD[eid] == int(e['fixedDi']))
        if e.get('fixedS') is not None:
            m.Add(evS[eid] == int(e['fixedS']))

    # PAIRED LECTURES (jaise CSE ke 2 lectures): same day + ek ke baad ek
    # (back-to-back) — par timetable me ALAG-ALAG cells (dono 1hr events).
    pairGroups = {}
    for e in events:
        pg = e.get('pairGroup')
        if pg:
            pairGroups.setdefault(pg, []).append(e)
    for pg, es in pairGroups.items():
        es = sorted(es, key=lambda x: x.get('occ', 0))
        for k in range(len(es) - 1):
            e1, e2 = es[k], es[k + 1]
            m.Add(evD[e1['id']] == evD[e2['id']])
            m.Add(evS[e2['id']] == evS[e1['id']] + 1)
            # CONTINUOUS: dono slots ke beech koi break nahi hona chahiye
            m.AddAllowedAssignments([evS[e1['id']]], [[x] for x in start2h])

    famEvents = {}
    for e in events:
        famEvents.setdefault(e['family'], []).append(e)
    for fam, es in famEvents.items():
        if len(es) > 1:
            m.AddAllDifferent([evD[e['id']] for e in es])

    divTheory = {}
    for e in events:
        if e['kind'] == 'theory':
            divTheory.setdefault(e['divisionName'], []).append(e['id'])
    for div, ids in divTheory.items():
        for di in range(nD):
            m.Add(sum(cover[(i, di, si)] for i in ids for si in range(nS)) >= 1)
    divWins = {}
    for e in events:
        if e['kind'] == 'lab' and e.get('windowId'):
            divWins.setdefault(e['divisionName'], set()).add(e['windowId'])
    for div, ws in divWins.items():
        for di in range(nD):
            bs = []
            for w in ws:
                b = m.NewBoolVar('wd_%s_%d' % (w, di))
                m.Add(winVars[w][0] == di).OnlyEnforceIf(b)
                m.Add(winVars[w][0] != di).OnlyEnforceIf(b.Not())
                bs.append(b)
            m.Add(sum(bs) >= 1)

    tutEvents = [e for e in events if e['kind'] == 'tutorial']
    for t in tutEvents:
        for g in t['participants']:
            for oid in batchEvents.get(g, []):
                if oid == t['id']:
                    continue
                o = next(e for e in events if e['id'] == oid)
                same = m.NewBoolVar('same_%s_%s' % (t['id'], oid))
                m.Add(evD[t['id']] == evD[oid]).OnlyEnforceIf(same)
                m.Add(evD[t['id']] != evD[oid]).OnlyEnforceIf(same.Not())
                m.Add(evS[t['id']] >= evS[oid] + o['duration']).OnlyEnforceIf(same)

    # ROOM FEASIBILITY: ek (day,slot) me itni divisions/events nahi jo rooms
    # me fit na hon (warna room assign karna impossible ho jata hai)
    divEvents = {}
    for e in events:
        divEvents.setdefault(e['divisionName'], []).append(e['id'])
    n_rooms = len(resources)
    tot_cap = sum(max(1, (r.get('capacity') or 1)) for r in resources)
    for di in range(nD):
        for si in range(nS):
            pres = []
            for dv, ids in divEvents.items():
                b = m.NewBoolVar('pres_%d_%d_%d' % (len(pres), di, si))
                for i in ids:
                    m.AddImplication(cover[(i, di, si)], b)
                pres.append(b)
            m.Add(sum(pres) <= n_rooms)
            m.Add(sum(cover[(e['id'], di, si)] for e in events) <= tot_cap)

    # PER-DEPT room capacity: ek (day,slot) me us dept ke rooms se zyada
    # events nahi (dept rule + capacity dono)
    deptEvents = {}
    for e in events:
        if e['kind'] not in ('lab', 'batch'):
            continue
        deptEvents.setdefault((e.get('roomDept') or ''), []).append(e['id'])
    deptCap = {}
    for r in resources:
        if r.get('onlyPinned'):
            continue
        d = (r.get('dept') or '')
        deptCap[d] = deptCap.get(d, 0) + max(1, (r.get('capacity') or 1))
    genCap = deptCap.get('GENERAL', 0) + deptCap.get('General', 0)
    for di in range(nD):
        for si in range(nS):
            for d, ids in deptEvents.items():
                cap = deptCap.get(d, 0) + (0 if (d or '').strip().upper() == 'GENERAL' else deptCap.get('GENERAL', 0))  # apne rooms + GENERAL (common)
                if cap <= 0:
                    continue
                m.Add(sum(cover[(i, di, si)] for i in ids) <= cap)

    # pinned rooms: ek time par ek hi division
    for R in [r['name'] for r in resources if r.get('onlyPinned')]:
        ids = [e['id'] for e in events if e.get('roomFixed') == R]
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                e1 = next(e for e in events if e['id'] == ids[a]); e2 = next(e for e in events if e['id'] == ids[b])
                if e1['divisionName'] == e2['divisionName']:
                    continue
                for di in range(nD):
                    for si in range(nS):
                        m.AddBoolOr([cover[(ids[a], di, si)].Not(), cover[(ids[b], di, si)].Not()])

    # LAB capacity (simple): ek slot me us dept ke lab batches <= us dept ke
    # lab rooms x 3 (warna room assign karna impossible ho jata hai)
    dept_lab_cap = {}
    for r in resources:
        if r.get('onlyPinned') or r['type'] != 'lab':
            continue
        d = (r.get('dept') or '').strip().upper()
        dept_lab_cap[d] = dept_lab_cap.get(d, 0) + 3

    def goes_to_labroom(e):
        if e.get('roomFixed') or e.get('labClassroom'):
            return False              # pinned / classroom-lab alag handle
        return True
    lr_ev = [e for e in events if e['kind'] in ('lab', 'batch') and goes_to_labroom(e)]
    for di in range(nD):
        for si in range(nS):
            m.Add(sum(cover[(e['id'], di, si)] for e in lr_ev) <= sum(dept_lab_cap.values()))
            for d, cap in dept_lab_cap.items():
                ids = [e['id'] for e in lr_ev if (e.get('roomDept') or '').strip().upper() == d]
                if ids:
                    m.Add(sum(cover[(i, di, si)] for i in ids) <= cap)

    # CLASSROOM capacity: ek slot me classrooms se zyada classroom-UNITS nahi.
    # UNIT = ek theory event / ek tutorial window / ek classroom-lab. (Division
    # se nahi ginn sakte: ek division ke 2 batches alag classrooms me ho sakte
    # hain — jaise A1+A2 tutorial + A3 kuch aur.)
    n_class = len([r for r in resources if not r.get('onlyPinned') and r['type'] == 'classroom'])
    cl_units = []
    tut_seen = set()
    for e in events:
        if e.get('roomFixed'):
            continue
        if e['kind'] == 'lab' and not e.get('labClassroom'):
            continue
        if e['kind'] == 'tutorial' and e.get('windowId'):
            if e['windowId'] in tut_seen:
                continue
            tut_seen.add(e['windowId'])
        cl_units.append(e['id'])
    for di in range(nD):
        for si in range(nS):
            m.Add(sum(cover[(i, di, si)] for i in cl_units) <= n_class)

    # per-dept: ek slot me us dept ke lab rooms se zyada DIVISIONS nahi
    # (ek lab room me sirf EK division ke batches — one-division-per-room rule)
    dept_lab_rooms = {}
    for r in resources:
        if r.get('onlyPinned') or r['type'] != 'lab':
            continue
        d = (r.get('dept') or '').strip().upper()
        dept_lab_rooms[d] = dept_lab_rooms.get(d, 0) + 1
    for d, nrooms in dept_lab_rooms.items():
        divs_d = {}
        for e in lr_ev:
            if (e.get('roomDept') or '').strip().upper() == d:
                divs_d.setdefault(e['divisionName'], []).append(e['id'])
        for di in range(nD):
            for si in range(nS):
                bs = []
                for dv, ids in divs_d.items():
                    b = m.NewBoolVar('dl_%s_%s_%d_%d' % (d, dv, di, si))
                    for i in ids:
                        m.AddImplication(cover[(i, di, si)], b)
                    bs.append(b)
                if bs:
                    m.Add(sum(bs) <= nrooms)

    # NOTE: objective (sum of start slots) hata diya — 2-core pod par
    # pure-feasibility solve bahut tez hota hai aur timetable equally valid.
    # Compact/early-schedule chahiye to niche wali line uncomment kar do.
    # m.Minimize(sum(evS[e['id']] for e in events))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = max(1, workers)
    solver.parameters.random_seed = seed
    solver.parameters.random_seed = seed
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {'status': 'INFEASIBLE' if st == cp_model.INFEASIBLE else 'UNKNOWN'}
    pl = {}
    for e in events:
        eid = e['id']
        pl[eid] = {'di': int(solver.Value(evD[eid])), 's': int(solver.Value(evS[eid])),
                   'room': evRooms[eid][int(solver.Value(rvars[eid]))]}
    # room assignment: tutorial window = EK unit (shared room); baaki per-event.
    # most-constrained-first + capacity + one-division-per-room.
    roomById = {r['name']: r for r in resources}
    units = []
    seen = set()
    for e in events:
        w = e.get('windowId')
        if w is not None and str(w).startswith('TW'):
            if w in seen:
                continue
            seen.add(w)
            units.append({'evs': [x for x in events if x.get('windowId') == w]})
        else:
            units.append({'evs': [e]})

    def allowed_for(u):
        common = None
        for e in u['evs']:
            rs = set(evRooms[e['id']])
            common = rs if common is None else (common & rs)
        return sorted(common) if common else sorted(evRooms[u['evs'][0]['id']])

    import random as _rnd
    base_order = sorted(units, key=lambda u: (len(allowed_for(u)), pl[u['evs'][0]['id']]['di'], pl[u['evs'][0]['id']]['s']))
    best_pl = None; best_fail = 10**9
    for attempt in range(60):
        order = base_order[:]
        if attempt > 0:
            _rnd.shuffle(order)
            order.sort(key=lambda u: len(allowed_for(u)) + _rnd.random() * 2)
        use = {}; divs = {}
        cur = {}
        fails = 0
        for u in order:
            cands = allowed_for(u)
            pick = None
            for r in cands:
                cap = max(1, roomById[r].get('capacity') or 1)
                ok = True
                for e in u['evs']:
                    p = pl[e['id']]
                    for q in range(e['duration']):
                        k = (r, p['di'], p['s'] + q)
                        if use.get(k, 0) + 1 > cap:
                            ok = False; break
                        ds = divs.get(k)
                        if ds and e['divisionName'] not in ds:
                            ok = False; break
                    if not ok:
                        break
                if ok:
                    pick = r; break
            if not pick:
                fails += 1
                # best-effort: least-loaded allowed room
                pick = min(cands, key=lambda r: use.get((r, pl[u['evs'][0]['id']]['di'], pl[u['evs'][0]['id']]['s']), 0))
            for e in u['evs']:
                p = pl[e['id']]
                cur[e['id']] = pick
                for q in range(e['duration']):
                    k = (pick, p['di'], p['s'] + q)
                    use[k] = use.get(k, 0) + 1
                    divs.setdefault(k, set()).add(e['divisionName'])
        if fails < best_fail:
            best_fail = fails; best_pl = cur
        if fails == 0:
            break
    if best_pl:
        for eid, room in best_pl.items():
            pl[eid]['room'] = room

    # ---- REPAIR: bache hue room conflicts ko move karke theek karo ----
    import random as _r2
    unit_of = {}   # eventId -> unit id
    units_list = []
    for u in units:
        uid = len(units_list)
        units_list.append(u)
        for e in u['evs']:
            unit_of[e['id']] = uid

    def occupancy():
        use = {}; divs = {}
        for u in units_list:
            r = pl[u['evs'][0]['id']]['room']
            for e in u['evs']:
                p = pl[e['id']]
                for q in range(e['duration']):
                    k = (r, p['di'], p['s'] + q)
                    use[k] = use.get(k, 0) + 1
                    divs.setdefault(k, set()).add(e['divisionName'])
        return use, divs

    def free_for(u, r):
        cap = max(1, roomById[r].get('capacity') or 1)
        for e in u['evs']:
            p = pl[e['id']]
            for q in range(e['duration']):
                k = (r, p['di'], p['s'] + q)
                if use.get(k, 0) + 1 > cap:
                    return False
                ds = divs.get(k)
                if ds and e['divisionName'] not in ds:
                    return False
        return True

    for _it in range(400):
        use, divs = occupancy()
        bad = None
        for (r, di, si), c in use.items():
            cap = max(1, roomById[r].get('capacity') or 1)
            ds = divs.get((r, di, si)) or set()
            if c > cap or len(ds) > 1:
                bad = (r, di, si)
                break
        if not bad:
            break
        # is room/slot me jo units hain, unme se kisi ko hatao
        moved = False
        cand_units = []
        for u in units_list:
            r = pl[u['evs'][0]['id']]['room']
            if r != bad[0]:
                continue
            for e in u['evs']:
                p = pl[e['id']]
                if p['di'] == bad[1] and p['s'] <= bad[2] < p['s'] + e['duration']:
                    cand_units.append(u); break
        _r2.shuffle(cand_units)
        for u in cand_units:
            opts = [x for x in allowed_for(u) if x != bad[0]]
            _r2.shuffle(opts)
            for r2 in opts:
                # temporarily remove this unit
                r_old = pl[u['evs'][0]['id']]['room']
                for e in u['evs']:
                    p = pl[e['id']]
                    for q in range(e['duration']):
                        k = (r_old, p['di'], p['s'] + q)
                        use[k] = use.get(k, 0) - 1
                        if use[k] == 0:
                            divs.pop(k, None)
                if free_for(u, r2):
                    for e in u['evs']:
                        pl[e['id']]['room'] = r2
                    moved = True
                    break
                else:
                    for e in u['evs']:
                        p = pl[e['id']]
                        for q in range(e['duration']):
                            k = (r_old, p['di'], p['s'] + q)
                            use[k] = use.get(k, 0) + 1
                            divs.setdefault(k, set()).add(e['divisionName'])
            if moved:
                break
        if not moved:
            break
    return {'status': 'OPTIMAL' if st == cp_model.OPTIMAL else 'FEASIBLE', 'placements': pl}


def _faculty_plan(sem_keys, sem_events, nD, nS):
    """Har faculty ke slots ko semesters me PROPORTIONALLY baanto (app ke
    facultyPlan jaisa). Warna ek semester sab slots kha jata hai aur baaki
    INFEASIBLE ho jate hain."""
    n = len(sem_keys)
    needs = {}
    for gi, k in enumerate(sem_keys):
        for e in sem_events[k]:
            for f in (e.get('faculties') or []):
                needs.setdefault(f, [0] * n)[gi] += int(e.get('duration') or 1)
    alloc = {}
    for f, need in needs.items():
        total = sum(need) or 1
        seed = 0
        for ch in f:
            seed = (seed * 31 + ord(ch)) & 0xFFFFFFFF
        fac_off = seed % n
        alloc[f] = {}
        for di in range(nD):
            raw = [(v / total) * nS for v in need]
            base = [int(x) for x in raw]
            rem = nS - sum(base)
            order = sorted(range(n), key=lambda i: -(raw[i] - int(raw[i])))
            for k in range(max(0, rem)):
                base[order[k % len(order)]] += 1
            remc = base[:]
            for k in range(nS):
                best, best_r = -1, -1
                for t in range(n):
                    s2 = (k + di + fac_off + t) % n
                    if remc[s2] > best_r:
                        best_r = remc[s2]; best = s2
                if best < 0:
                    best = (k + di + fac_off) % n
                alloc[f][(di, k)] = best
                if remc[best] > 0:
                    remc[best] -= 1
    return alloc


def solve(data, time_limit=240, workers=8, seed=0):
    """SEMESTER-WISE solve: har semester alag solve hota hai (chhote problem
    bahut tez) aur faculty ke slots PEHLE se proportionally reserve kar diye
    jate hain (cross-semester clash nahi hota). Kamzor/free server par bhi
    solve ho jata hai."""
    events = data.get('events') or []
    sem = {}
    for e in events:
        key = str(e.get('divisionName') or e.get('division') or '').split('-')[0] or 'all'
        sem.setdefault(key, []).append(e)
    if len(sem) <= 1:
        return _solve_once(data, time_limit, workers, seed)

    keys = sorted(sem.keys())

    try:
        r = _solve_semesters(data, keys, sem, time_limit, workers, seed)
        if r.get('status') in ('OPTIMAL', 'FEASIBLE') and r.get('placements'):
            return r
    except Exception:
        pass
    # fallback: poora ek saath solve (dheema par sahi)
    return _solve_once(data, time_limit, workers, seed)


def _solve_semesters(data, keys, sem, time_limit, workers, seed):
    slots = data.get('slots') or []
    days = data.get('days') or []
    nD, nS = len(days), len(slots)
    alloc = _faculty_plan(keys, sem, nD, nS)
    per = max(15, int(time_limit / len(keys)))
    placements = {}
    statuses = []
    for i, k in enumerate(keys):
        blocked = {}
        for f, amap in alloc.items():
            blk = [list(pos) for pos, gi in amap.items() if gi != i]
            if blk:
                blocked[f] = blk
        sub = dict(data)
        sub['events'] = sem[k]
        sub['blockFac'] = blocked
        r = _solve_once(sub, per, workers, seed + i * 7)
        st = r.get('status')
        if st not in ('OPTIMAL', 'FEASIBLE'):
            r = _solve_once(sub, max(per, 45), workers, seed + 100 + i)
            st = r.get('status')
        statuses.append(st)
        if st not in ('OPTIMAL', 'FEASIBLE'):
            return {'status': 'UNKNOWN', 'placements': {}, 'failed_semester': k, 'sem_status': statuses}
        placements.update(r.get('placements') or {})
    return {'status': 'FEASIBLE', 'placements': placements, 'sem_status': statuses}
