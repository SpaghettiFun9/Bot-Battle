import math
from helper.game import Game
from lib.interface.events.moves.move_player import MovePlayer
from lib.interface.queries.query_move import QueryMovePlayer
from lib.models.penguin_model import DirectionModel
from lib.config.arena import ARENA_SIZE, MAX_ROUNDS, VIRUS_SIZE, MAX_BLOB_COUNT
from lib.config.player import (
    EAT_SIZE_RATIO,
    BASE_PLAYER_SPEED,
    PLAYER_SPEED_RADIUS_FACTOR,
    MIN_PLAYER_SPEED,
    SPLIT_MIN_MASS,
    SPLIT_EJECT_SPEED,
    SPLIT_EJECT_DRAG
)

# kevin_bot_v39

MAP_MAX = ARENA_SIZE
EAT_RATIO = EAT_SIZE_RATIO
SPLIT_RATIO = 2.4
SPLIT_JUMP = SPLIT_EJECT_SPEED / (1.0 - SPLIT_EJECT_DRAG)
MAX_BLOBS = MAX_BLOB_COUNT
VIRUS_CONSUME_MASS = (VIRUS_SIZE ** 2) * EAT_SIZE_RATIO
NEAR_THREAT_RATIO = 0.92
NUM_RAYS = 36


def blob_speed(radius):
    return max(MIN_PLAYER_SPEED, BASE_PLAYER_SPEED / (1.0 + radius * PLAYER_SPEED_RADIUS_FACTOR))


class BotMemory:
    def __init__(self):
        self.last_positions = {}
        self.velocities = {}
        self.last_dir = (1.0, 0.0)
        self.visit_history = []
        self.tick = 0
        self.my_last_pos = None
        self.rays = [(math.cos(i * 2 * math.pi / NUM_RAYS),
                      math.sin(i * 2 * math.pi / NUM_RAYS)) for i in range(NUM_RAYS)]


def calculate_move(query: QueryMovePlayer, memory: BotMemory) -> MovePlayer:
    if not query.you.alive or not query.you.blobs:
        return MovePlayer(
            player_id=query.you.player_id,
            direction=DirectionModel(x=1.0, y=0.0),
            split=False
        )

    my_blobs = query.you.blobs
    my_blob_count = len(my_blobs)
    my_total_mass = sum(b.radius * b.radius for b in my_blobs)

    my_largest = max(my_blobs, key=lambda b: b.radius)
    my_x, my_y = my_largest.pos
    my_r = my_largest.radius
    my_largest_mass = my_r * my_r

    my_vx, my_vy = 0.0, 0.0
    if memory.my_last_pos:
        my_vx = my_x - memory.my_last_pos[0]
        my_vy = my_y - memory.my_last_pos[1]
    memory.my_last_pos = (my_x, my_y)

    memory.tick += 1
    if memory.tick % 5 == 0:
        memory.visit_history.append((my_x, my_y, memory.tick))
    memory.visit_history = [
        h for h in memory.visit_history if memory.tick - h[2] < 200]

    enemy_player_masses = {}
    enemy_player_blob_counts = {}
    for b in query.visible_blobs:
        if b.player_id == query.you.player_id:
            continue
        enemy_player_masses[b.player_id] = enemy_player_masses.get(
            b.player_id, 0.0) + (b.radius * b.radius)
        enemy_player_blob_counts[b.player_id] = enemy_player_blob_counts.get(
            b.player_id, 0) + 1

    current_blob_ids = set()
    enemy_data = []
    can_physically_split = my_blob_count < MAX_BLOBS and my_largest_mass > SPLIT_MIN_MASS

    for b in query.visible_blobs:
        if b.player_id == query.you.player_id:
            continue

        b_id = getattr(b, 'blob_id', id(b))
        current_blob_ids.add(b_id)

        dx_lg = b.pos[0] - my_x
        dy_lg = b.pos[1] - my_y
        dist_sq = dx_lg * dx_lg + dy_lg * dy_lg

        if dist_sq < 0.0001:
            continue

        dist_lg = math.sqrt(dist_sq)

        vx, vy = 0.0, 0.0
        if b_id in memory.last_positions:
            lx, ly = memory.last_positions[b_id]
            vx = b.pos[0] - lx
            vy = b.pos[1] - ly
            if b_id in memory.velocities:
                ovx, ovy = memory.velocities[b_id]
                vx = vx * 0.5 + ovx * 0.5

        memory.last_positions[b_id] = b.pos
        memory.velocities[b_id] = (vx, vy)

        enemy_mass = b.radius * b.radius
        enemy_cd = getattr(b, 'merge_cooldown', 0)

        threatened_mbs = [mb for mb in my_blobs if enemy_mass >= (
            mb.radius * mb.radius) * EAT_RATIO]
        is_threat = len(threatened_mbs) > 0
        is_split_threat = False

        threat_ox, threat_oy, threat_dist = 0.0, 0.0, 999.0
        vuln_r = 0.0
        if is_threat:
            vuln_mb = min(threatened_mbs, key=lambda mb: (
                b.pos[0]-mb.pos[0])*(b.pos[0]-mb.pos[0]) + (b.pos[1]-mb.pos[1])*(b.pos[1]-mb.pos[1]))
            threat_ox = b.pos[0] - vuln_mb.pos[0]
            threat_oy = b.pos[1] - vuln_mb.pos[1]
            threat_dist = math.sqrt(
                threat_ox * threat_ox + threat_oy * threat_oy)
            vuln_r = vuln_mb.radius
            is_split_threat = enemy_mass >= (
                vuln_mb.radius * vuln_mb.radius) * SPLIT_RATIO

        is_prey = my_largest_mass >= enemy_mass * EAT_RATIO
        is_split_target = is_prey and my_largest_mass / \
            2.0 >= enemy_mass * EAT_RATIO and can_physically_split

        # v37 Merge-Trap Integration
        if is_split_target and enemy_cd == 0 and enemy_player_blob_counts.get(b.player_id, 0) > 1:
            if (my_largest_mass / 2.0) < enemy_player_masses.get(b.player_id, 0) * EAT_RATIO:
                is_split_target = False

        ratio = enemy_mass / my_largest_mass if my_largest_mass > 0 else 0.0
        is_near_threat = (not is_threat) and ratio >= NEAR_THREAT_RATIO
        near_danger = 0.0
        if is_near_threat:
            nd = (ratio - NEAR_THREAT_RATIO) / (EAT_RATIO - NEAR_THREAT_RATIO)
            near_danger = max(0.0, min(1.0, nd))
            near_danger *= near_danger

        heading_to_wall = False
        if abs(vx) > 0.05 or abs(vy) > 0.05:
            tx = (MAP_MAX - b.pos[0]) / vx if vx > 0 else (
                b.pos[0] / -vx if vx < 0 else float('inf'))
            ty = (MAP_MAX - b.pos[1]) / vy if vy > 0 else (
                b.pos[1] / -vy if vy < 0 else float('inf'))
            if min(tx, ty) < 15.0:
                heading_to_wall = True

        enemy_wall_dist = min(b.pos[0], MAP_MAX -
                              b.pos[0], b.pos[1], MAP_MAX - b.pos[1])
        cornered = enemy_wall_dist < 10.0 or heading_to_wall

        target_dir_x, target_dir_y = dx_lg / dist_lg, dy_lg / dist_lg
        threat_dir_x = threat_ox / threat_dist if threat_dist > 0.01 else 0.0
        threat_dir_y = threat_oy / threat_dist if threat_dist > 0.01 else 0.0

        if is_prey and cornered:
            EDGE_BAND = 10.0
            fx, fy = b.pos[0] - my_x, b.pos[1] - my_y
            fmag = math.sqrt(fx * fx + fy * fy)
            if fmag > 0.01:
                fx, fy = fx / fmag, fy / fmag
            if b.pos[0] < EDGE_BAND and fx < 0:
                fx = 0.0
            if b.pos[0] > MAP_MAX - EDGE_BAND and fx > 0:
                fx = 0.0
            if b.pos[1] < EDGE_BAND and fy < 0:
                fy = 0.0
            if b.pos[1] > MAP_MAX - EDGE_BAND and fy > 0:
                fy = 0.0

            emag = math.sqrt(fx * fx + fy * fy)
            if emag > 0.01:
                gx, gy = fx / emag, fy / emag
                vmag = math.sqrt(vx * vx + vy * vy)
                if vmag > 0.01:
                    px = gx * 0.6 + (vx / vmag) * 0.4
                    py = gy * 0.6 + (vy / vmag) * 0.4
                else:
                    px, py = gx, gy
                pmag = math.sqrt(px * px + py * py)
                if pmag > 0.01:
                    px, py = px / pmag, py / pmag
                lead = min(dist_lg, 9.0)
                aim_x = b.pos[0] + px * lead
                aim_y = b.pos[1] + py * lead
                adx, ady = aim_x - my_x, aim_y - my_y
                amag = math.sqrt(adx * adx + ady * ady)
                if amag > 0.01:
                    target_dir_x, target_dir_y = adx / amag, ady / amag

        enemy_data.append({
            'x': b.pos[0], 'y': b.pos[1], 'vx': vx, 'vy': vy,
            'dist': dist_lg, 'dir_x': target_dir_x, 'dir_y': target_dir_y,
            'is_threat': is_threat, 'is_split_threat': is_split_threat,
            'threat_dist': threat_dist, 'threat_dir_x': threat_dir_x, 'threat_dir_y': threat_dir_y, 'vuln_r': vuln_r,
            'is_prey': is_prey, 'is_split_target': is_split_target, 'cd': enemy_cd,
            'is_near_threat': is_near_threat, 'near_danger': near_danger,
            'cornered': cornered, 'r': b.radius, 'pid': b.player_id, 'mass': enemy_mass
        })

    flee_pressure = 0.0
    for e in enemy_data:
        if e['is_threat'] and e['threat_dist'] < 18.0:
            _fp = (18.0 - e['threat_dist']) / 18.0
            if _fp > flee_pressure:
                flee_pressure = _fp

    hypothetical_fragment_mass = (
        my_total_mass + VIRUS_CONSUME_MASS) / MAX_BLOBS
    safe_to_farm = True

    # Endgame Virus Confidence: Scales threat radius based on enemy reach instead of a static 40u blanket
    for e in enemy_data:
        if e['mass'] >= hypothetical_fragment_mass * EAT_RATIO:
            dynamic_farm_radius = max(18.0, e['r'] * 2.5 + 8.0)
            if e['dist'] < dynamic_farm_radius:
                safe_to_farm = False
                break

    farm_viruses = (safe_to_farm or my_blob_count ==
                    MAX_BLOBS) and my_largest_mass > VIRUS_CONSUME_MASS

    virus_pts = []
    if query.visible_viruses:
        for v in query.visible_viruses:
            vuln_mbs = [mb for mb in my_blobs if (
                mb.radius * mb.radius) > VIRUS_CONSUME_MASS]
            if vuln_mbs:
                bmb = min(vuln_mbs, key=lambda mb: (
                    v.pos[0]-mb.pos[0])*(v.pos[0]-mb.pos[0]) + (v.pos[1]-mb.pos[1])*(v.pos[1]-mb.pos[1]))
                ox, oy = v.pos[0] - bmb.pos[0], v.pos[1] - bmb.pos[1]
                virus_pts.append((ox, oy, bmb.radius))

    food_pts = []
    if query.visible_food:
        for f in query.visible_food:
            bd2 = 1e18
            bmb = my_blobs[0]
            fx, fy = f.pos
            for mb in my_blobs:
                dx = fx - mb.pos[0]
                dy = fy - mb.pos[1]
                d2 = dx * dx + dy * dy
                if d2 < bd2:
                    bd2 = d2
                    bmb = mb

            if bd2 < 625.0:
                food_pts.append(
                    (fx - bmb.pos[0], fy - bmb.pos[1], bmb.radius + 0.15))

    cornered_prey = [e for e in enemy_data if e['cornered'] and e['is_prey']]

    best_score = -float('inf')
    best_ray = memory.last_dir
    do_split = False

    mass_aggression_multiplier = 1.0 + (my_largest_mass / 200.0)
    snowball_aggro = 1.0
    endgame_caution = 1.0

    try:
        rank = list(query.rankings).index(query.you.player_id)
    except:
        rank = 4

    if my_total_mass > 25.0:
        snowball_aggro += (my_total_mass - 25.0) / 40.0
        if rank <= 1:
            snowball_aggro += 0.5
        # Endgame Threat Floor: Raised from 0.4 to 0.75 to prevent ignoring massive predators in late game
        endgame_caution = max(0.75, 1.0 - (my_total_mass / 250.0))
    elif my_largest_mass < 10.0 and (MAX_ROUNDS - query.round) < 500:
        endgame_caution = 1.5

    # Early-Game Greed Cancellation: Smooth scaling, immediately drops if any flee pressure exists
    early_game_boost = 1.0
    if my_total_mass < 35.0:
        early_game_boost = 1.0 + 1.5 * ((35.0 - my_total_mass) / 35.0)
        if flee_pressure > 0.1:
            early_game_boost = 1.0

    for rx, ry in memory.rays:
        score = 0.0
        chase_food_mult = 1.0 * mass_aggression_multiplier * early_game_boost
        ray_prey_score = 0.0

        score += (rx * memory.last_dir[0] + ry * memory.last_dir[1]) * 15.0

        proj_x = my_x + rx * 12.0
        proj_y = my_y + ry * 12.0
        for hx, hy, htick in memory.visit_history:
            hdx = proj_x - hx
            hdy = proj_y - hy
            if hdx * hdx + hdy * hdy < 100.0:
                age_ratio = 1.0 - ((memory.tick - htick) / 200.0)
                score -= 2.0 * max(0.0, age_ratio)

        for e in enemy_data:
            if e['is_threat']:
                t_dot = rx * e['threat_dir_x'] + ry * e['threat_dir_y']
                if t_dot > 0.1:
                    weight = (45000.0 if e['is_split_threat']
                              else 20000.0) * endgame_caution
                    score -= (weight * t_dot) / \
                        max(1.0, e['threat_dist'] * e['threat_dist'])

                    lunge = e['r'] + \
                        (SPLIT_JUMP if e['is_split_threat'] else 2.0)
                    if e['threat_dist'] < lunge + e['vuln_r']:
                        score -= 1e9

            elif e['is_near_threat']:
                n_dot = rx * (e['x'] - my_x) / e['dist'] + \
                    ry * (e['y'] - my_y) / e['dist']
                if n_dot > 0.3:
                    score -= (12000.0 * e['near_danger'] * endgame_caution *
                              n_dot) / max(1.0, e['dist'] * e['dist'])

            if e['is_prey']:
                p_dot = rx * e['dir_x'] + ry * e['dir_y']
                if p_dot > 0.3:
                    mass_utility = min(
                        1.0, e['mass'] / (my_total_mass * 0.04 + 1.0))

                    if e['cornered'] and mass_utility < 0.15:
                        mass_utility *= 0.1

                    cd_bonus = 1.5 if e['cd'] > 0 else 1.0

                    if e['cornered']:
                        add_score = (50000.0 * p_dot * mass_aggression_multiplier *
                                     snowball_aggro * mass_utility * cd_bonus) / max(0.1, e['dist'])
                        score += add_score
                        ray_prey_score += add_score
                        chase_food_mult = max(
                            chase_food_mult, 1.5 * mass_aggression_multiplier)
                    else:
                        add_score = (4000.0 * p_dot * mass_aggression_multiplier *
                                     snowball_aggro * mass_utility * cd_bonus) / max(1.0, e['dist'])
                        score += add_score
                        ray_prey_score += add_score
                        if p_dot > 0.85:
                            chase_food_mult = max(
                                chase_food_mult, 4.0 if not e['is_split_target'] else 2.0)

        dist_x = (MAP_MAX - my_x) / rx if rx > 0 else (my_x / -
                                                       rx if rx < 0 else float('inf'))
        dist_y = (MAP_MAX - my_y) / ry if ry > 0 else (my_y / -
                                                       ry if ry < 0 else float('inf'))
        wall_dist = min(dist_x, dist_y)
        edge_wall_dist = wall_dist - my_r

        if flee_pressure > 0.0 and edge_wall_dist < 14.0:
            score -= 3000.0 * flee_pressure * (14.0 - edge_wall_dist) / 14.0

        if edge_wall_dist < 2.0:
            base_wall_penalty = 4000.0 / max(0.1, edge_wall_dist + 0.5)

            is_executing_cornered = False
            if ray_prey_score > 0 and cornered_prey:
                for cp in cornered_prey:
                    if rx * cp['dir_x'] + ry * cp['dir_y'] > 0.85:
                        is_executing_cornered = True
                        break

            if is_executing_cornered:
                score -= 0.0
            elif ray_prey_score > 0:
                score -= base_wall_penalty * 0.05
            else:
                score -= base_wall_penalty

        if my_blob_count < MAX_BLOBS and not farm_viruses:
            for ox, oy, br in virus_pts:
                along_dist = rx * ox + ry * oy
                if 0 < along_dist < 30.0:
                    perp_dist = abs(rx * oy - ry * ox)
                    if perp_dist < (br + 0.1):
                        score -= 1e9
        elif farm_viruses:
            for ox, oy, br in virus_pts:
                along_dist = rx * ox + ry * oy
                if 0 < along_dist < 30.0:
                    perp_dist = abs(rx * oy - ry * ox)
                    if perp_dist < (br + 0.1):
                        score += (25000.0 * snowball_aggro) / \
                            (along_dist + 1.0)

        if food_pts:
            fs = 0.0
            for ox, oy, er in food_pts:
                along_dist = rx * ox + ry * oy
                if 0 < along_dist < 25.0:
                    perp_dist = abs(rx * oy - ry * ox)
                    if perp_dist < er:
                        accuracy_mult = 1.0 - (perp_dist / er)
                        fs += (75.0 * (1.0 + 2.0 * accuracy_mult) *
                               chase_food_mult * snowball_aggro) / (along_dist + 1.0)
            score += fs

        if score > best_score:
            best_score = score
            best_ray = (rx, ry)

    if can_physically_split:
        halved_mass = my_largest_mass / 2.0
        halved_r = math.sqrt(halved_mass)
        landing_x = my_x + best_ray[0] * (halved_r + SPLIT_JUMP)
        landing_y = my_y + best_ray[1] * (halved_r + SPLIT_JUMP)

        safe_to_split = True
        for e in enemy_data:
            if e['mass'] >= halved_mass * EAT_RATIO:
                lx = landing_x - e['x']
                ly = landing_y - e['y']
                dist_to_landing = math.sqrt(lx * lx + ly * ly)
                lunge = e['r'] * 2.0 + \
                    (SPLIT_JUMP if e['is_split_threat'] else 0.0)
                if dist_to_landing < lunge + 4.0:
                    safe_to_split = False
                    break

        if safe_to_split:
            for e in enemy_data:
                if e['is_split_target']:
                    ex_future = max(0.0, min(MAP_MAX, e['x'] + e['vx'] * 6.0))
                    ey_future = max(0.0, min(MAP_MAX, e['y'] + e['vy'] * 6.0))

                    lcx = landing_x - e['x']
                    lcy = landing_y - e['y']
                    lfx = landing_x - ex_future
                    lfy = landing_y - ey_future

                    hit_current = math.sqrt(
                        lcx * lcx + lcy * lcy) < (halved_r - 0.2)
                    hit_future = math.sqrt(
                        lfx * lfx + lfy * lfy) < (halved_r - 0.2)

                    if hit_current or hit_future:
                        virus_blocked = False
                        if query.visible_viruses and my_blob_count < MAX_BLOBS:
                            for v in query.visible_viruses:
                                if halved_mass > VIRUS_CONSUME_MASS:
                                    vdx = v.pos[0] - my_x
                                    vdy = v.pos[1] - my_y
                                    vdot = best_ray[0] * \
                                        vdx + best_ray[1] * vdy
                                    if 0 < vdot < (halved_r + SPLIT_JUMP + v.radius):
                                        perp = abs(
                                            best_ray[0] * vdy - best_ray[1] * vdx)
                                        if perp < (halved_r + 0.1):
                                            virus_blocked = True
                                            break
                        if not virus_blocked:
                            do_split = True
                            break

        if not do_split and 22.0 < my_total_mass < 60.0 and my_blob_count < 3:
            no_threats_wide = not any(
                e['mass'] >= halved_mass * NEAR_THREAT_RATIO for e in enemy_data if e['dist'] < 45.0)
            if no_threats_wide and (MAX_ROUNDS - query.round) > 200:
                do_split = True

        if (not do_split and snowball_aggro > 1.5 and my_blob_count <= 6 and my_largest_mass > 40.0):
            no_threat_anywhere = not any(
                e['mass'] >= halved_mass * EAT_RATIO for e in enemy_data)
            virus_ahead = False
            if halved_mass > VIRUS_CONSUME_MASS and query.visible_viruses and my_blob_count < MAX_BLOBS:
                for v in query.visible_viruses:
                    vdx = v.pos[0] - my_x
                    vdy = v.pos[1] - my_y
                    vdot = best_ray[0] * vdx + best_ray[1] * vdy
                    if 0 < vdot < (halved_r + SPLIT_JUMP + v.radius):
                        if abs(best_ray[0] * vdy - best_ray[1] * vdx) < (halved_r + 0.1):
                            virus_ahead = True
                            break
            if no_threat_anywhere and not virus_ahead:
                do_split = True

    blend = 0.4
    smooth_x = best_ray[0] * (1.0 - blend) + memory.last_dir[0] * blend
    smooth_y = best_ray[1] * (1.0 - blend) + memory.last_dir[1] * blend

    mag = math.sqrt(smooth_x * smooth_x + smooth_y * smooth_y)
    if mag > 0.0001:
        smooth_x /= mag
        smooth_y /= mag

    if my_blob_count < MAX_BLOBS and not farm_viruses:
        for ox, oy, br in virus_pts:
            along = smooth_x * ox + smooth_y * oy
            perp = abs(smooth_x * oy - smooth_y * ox)
            if 0 < along < (br + VIRUS_SIZE + 1.0) and perp < (br + 0.1):
                smooth_x, smooth_y = best_ray[0], best_ray[1]
                break

    for e in enemy_data:
        if e['is_threat']:
            along = smooth_x * e['threat_dir_x'] * e['threat_dist'] + \
                smooth_y * e['threat_dir_y'] * e['threat_dist']
            perp = abs(smooth_x * e['threat_dir_y'] * e['threat_dist'] -
                       smooth_y * e['threat_dir_x'] * e['threat_dist'])
            lunge_zone = (SPLIT_JUMP if e['is_split_threat'] else 2.0)
            if 0 < along < (e['vuln_r'] + e['r'] + lunge_zone) and perp < (e['vuln_r'] + e['r'] - 0.2):
                smooth_x, smooth_y = best_ray[0], best_ray[1]
                break

    memory.last_dir = (smooth_x, smooth_y)

    return MovePlayer(
        player_id=query.you.player_id,
        direction=DirectionModel(x=smooth_x, y=smooth_y),
        split=do_split
    )


def main() -> None:
    game = Game()
    memory = BotMemory()
    while True:
        query = game.get_next_query()
        match query:
            case QueryMovePlayer():
                game.send_move(calculate_move(query, memory))
            case _:
                raise RuntimeError(f"Unsupported query type: {type(query)}")


if __name__ == "__main__":
    main()
