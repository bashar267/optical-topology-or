import ncs
from ncs.dp import Action
import ncs.maagic
import ncs.maapi
import ncs.log as ncs_log
import re


# ----------------------------------------------------------------------
# Helper: Parse interface names (DEG / SRG / MC / NMC / OMS / OTS)
# ----------------------------------------------------------------------
def parse_if_name(if_name: str):
    """
    Parse OpenROADM-ish interface names, e.g.:
      - MC-TTP-DEG1-RX-193.3
      - NMC-CTP-DEG1-TX-193.3
      - SRG1-PP01-TX-193.3
      - OMS-DEG1-TTP-RX
      - OTS-DEG2-TTP-TX

    Returns a dict with:
      layer ∈ {OMS, OTS, MC, NMC, None}
      degree_id, srg_id, pp_id (ints or None)
      direction ∈ {RX, TX, BIDIR, None}
      frequency (string or None)
    """
    parts = if_name.split('-')
    info = {
        'layer': None,
        'degree_id': None,
        'srg_id': None,
        'pp_id': None,
        'direction': None,
        'frequency': None,
    }

    if not parts:
        return info

    # Direction
    if 'RX' in parts:
        info['direction'] = 'RX'
    elif 'TX' in parts:
        info['direction'] = 'TX'

    # Frequency: last token if it looks like float
    last = parts[-1]
    try:
        float(last)
        info['frequency'] = last
    except Exception:
        pass

    # Degree / SRG / PP
    for p in parts:
        if p.startswith('DEG'):
            try:
                info['degree_id'] = int(p[3:])
            except Exception:
                pass
        elif p.startswith('SRG'):
            # SRG1, SRG2, ...
            m = re.match(r"SRG(\d+)", p)
            if m:
                try:
                    info['srg_id'] = int(m.group(1))
                except Exception:
                    pass
        elif p.startswith('PP'):
            # PP01, PP1, PP02...
            m = re.match(r"PP0*(\d+)", p)
            if m:
                try:
                    info['pp_id'] = int(m.group(1))
                except Exception:
                    pass

    prefix = parts[0]

    # Layer detection
    if prefix in ('OMS', 'OTS', 'MC', 'NMC'):
        info['layer'] = prefix
    elif prefix.startswith('SRG'):
        # SRG PP interfaces are NMC CTPs
        info['layer'] = 'NMC'

    return info


# ----------------------------------------------------------------------
# Helper: ensure MC interfaces on DEG side
# ----------------------------------------------------------------------
def ensure_mc_deg(dev, degree: int, direction: str, freq_str: str) -> str:
    """
    Ensure MC-TTP-DEG<degree>-<direction>-<freq> on DEG side.

    direction: "RX" or "TX"
    freq_str: e.g. "193.3"
    """
    if_name = f"MC-TTP-DEG{degree}-{direction}-{freq_str}"
    if_list = dev.config.org_openroadm_device__org_openroadm_device.interface

    if if_name in if_list:
        return if_name

    intf = if_list.create(if_name)

    # Type as in config.xml (identityref)
    # In CLI this typically shows as openROADM-if:mediaChannelTrailTerminationPoint
    intf.type = "openROADM-if:mediaChannelTrailTerminationPoint"
    intf.administrative_state = "inService"

    if direction == "RX":
        intf.supporting_circuit_pack_name = f"DEG{degree}-AMPRX"
        intf.supporting_port = f"DEG{degree}-AMPRX-IN"
        oms_if = f"OMS-DEG{degree}-TTP-RX"
    else:
        intf.supporting_circuit_pack_name = f"DEG{degree}-AMPTX"
        intf.supporting_port = f"DEG{degree}-AMPTX-OUT"
        oms_if = f"OMS-DEG{degree}-TTP-TX"

    # Single supporting interface in the list
    intf.supporting_interface_list = [oms_if]

    # Frequency slot: ±0.05 THz around center
    f = float(freq_str)
    minf = f - 0.05
    maxf = f + 0.05

    # The model uses decimal64, set as formatted strings
    intf.mc_ttp.min_freq = f"{minf:.2f}"
    intf.mc_ttp.max_freq = f"{maxf:.2f}"

    return if_name


# ----------------------------------------------------------------------
# Helper: ensure NMC interfaces on DEG side
# ----------------------------------------------------------------------
def ensure_nmc_deg(dev, degree: int, direction: str, freq_str: str) -> str:
    """
    Ensure NMC-CTP-DEG<degree>-<direction>-<freq> on DEG side.

    direction: "RX" or "TX"
    freq_str: e.g. "193.3"
    """
    if_name = f"NMC-CTP-DEG{degree}-{direction}-{freq_str}"
    if_list = dev.config.org_openroadm_device__org_openroadm_device.interface

    if if_name in if_list:
        return if_name

    intf = if_list.create(if_name)
    intf.type = "openROADM-if:networkMediaChannelConnectionTerminationPoint"
    intf.administrative_state = "inService"

    if direction == "RX":
        intf.supporting_circuit_pack_name = f"DEG{degree}-AMPRX"
        intf.supporting_port = f"DEG{degree}-AMPRX-IN"
        mc_if = f"MC-TTP-DEG{degree}-RX-{freq_str}"
    else:
        intf.supporting_circuit_pack_name = f"DEG{degree}-AMPTX"
        intf.supporting_port = f"DEG{degree}-AMPTX-OUT"
        mc_if = f"MC-TTP-DEG{degree}-TX-{freq_str}"

    # Link to the MC interface
    intf.supporting_interface_list = [mc_if]

    intf.nmc_ctp.frequency = freq_str
    intf.nmc_ctp.width = "100"

    return if_name


# ----------------------------------------------------------------------
# Helper: ensure NMC interfaces on SRG1 (PP ports)
# ----------------------------------------------------------------------
def ensure_nmc_srg_pp(dev, pp: int, direction: str, freq_str: str) -> str:
    """
    Ensure SRG1-PP<pp>-<direction>-<freq> on SRG side.

    Only NMC; no MC on SRG.

    direction: "RX" or "TX"
    pp: PP port index (1..6)
    """
    # SRG index fixed to 1 for now
    if_name = f"SRG1-PP{pp:02d}-{direction}-{freq_str}"
    if_list = dev.config.org_openroadm_device__org_openroadm_device.interface

    if if_name in if_list:
        return if_name

    intf = if_list.create(if_name)

    intf.type = "openROADM-if:networkMediaChannelConnectionTerminationPoint"
    intf.administrative_state = "inService"
    intf.supporting_circuit_pack_name = "SRG1-WSS"

    if direction == "RX":
        intf.supporting_port = f"SRG1-IN{pp}"
    else:
        intf.supporting_port = f"SRG1-OUT{pp}"

    intf.nmc_ctp.frequency = freq_str
    intf.nmc_ctp.width = "100"

    return if_name


# ----------------------------------------------------------------------
# Helper: check MC slot overlap on DEG
# ----------------------------------------------------------------------
def _slot_overlaps(dev, degree: int, direction: str, freq_str: str) -> bool:
    """
    Return True if proposed [f-0.05, f+0.05] overlaps any existing
    MC-TTP-DEG<degree>-<direction>-* slot.
    """
    try:
        f = float(freq_str)
    except Exception:
        return False  # malformed frequency, let device complain later

    new_min = f - 0.05
    new_max = f + 0.05

    if_list = dev.config.org_openroadm_device__org_openroadm_device.interface

    for intf in if_list:
        name = str(intf.name)
        if not name.startswith(f"MC-TTP-DEG{degree}-{direction}-"):
            continue
        if not hasattr(intf, "mc_ttp"):
            continue

        try:
            cur_min = float(str(intf.mc_ttp.min_freq))
            cur_max = float(str(intf.mc_ttp.max_freq))
        except Exception:
            continue

        # overlap if intervals intersect
        if not (new_max <= cur_min or new_min >= cur_max):
            return True

    return False


# ------------------------------------------------------------
#  DISCOVER TOPOLOGY  (DEG + SRG + Connections)
# ------------------------------------------------------------
class DiscoverTopology(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output):
        log = ncs_log.Log("optical-discovery")

        with ncs.maapi.single_write_trans(
            uinfo.username,
            uinfo.context,
            db=ncs.OPERATIONAL
        ) as t:

            root = ncs.maagic.get_root(t)

            # Prefix is **ot**
            topo = root.ot__optical_topology

            # Clear old topology
            del topo.node[:]
            del topo.connection[:]

            devs = input.device or [
                d.name for d in root.ncs__devices.device
            ]

            for dev_name in devs:
                try:
                    dev = root.ncs__devices.device[dev_name]
                except Exception:
                    continue

                # ---------------------------
                # Create NODE
                # ---------------------------
                node = topo.node.create(dev_name)
                node.device = dev_name
                if dev.address:
                    node.mgmt_ip = dev.address

                # ---------------------------
                # SRG & DEG DISCOVERY (from circuit-packs)
                # ---------------------------
                try:
                    cpacks = dev.config.org_openroadm_device__org_openroadm_device.circuit_packs
                except Exception:
                    cpacks = []

                for cp in cpacks:
                    cpname = str(cp.circuit_pack_name)

                    # Detect degrees: DEG1-AMP*, DEG2-AMP*, etc…
                    m_deg = re.match(r"DEG(\d+)-", cpname)
                    if m_deg:
                        deg_id = int(m_deg.group(1))
                        if deg_id not in node.degree:
                            node.degree.create(deg_id)
                        continue

                    # Detect SRG: SRG1-WSS, SRG1-IN*, SRG1-OUT*
                    m_srg = re.match(r"SRG(\d+)", cpname)
                    if m_srg:
                        srg_id = int(m_srg.group(1))
                        if srg_id not in node.srg:
                            node.srg.create(srg_id)
                        continue

                # ---------------------------
                # INTERFACE DISCOVERY (TPs)
                # ---------------------------
                try:
                    intfs = dev.config.org_openroadm_device__org_openroadm_device.interface
                except Exception:
                    intfs = []

                for intf in intfs:
                    if_name = str(intf.name)
                    info = parse_if_name(if_name)

                    tp = node.tp.create(if_name)
                    # tp.name = if_name  # key already set automatically
                    tp.interface = if_name

                    if info["layer"]:
                        tp.layer = info["layer"]

                    # DEG
                    if info["degree_id"] is not None:
                        deg_id = info["degree_id"]
                        if deg_id not in node.degree:
                            node.degree.create(deg_id)
                        tp.degree_id = deg_id

                    # SRG
                    if info["srg_id"] is not None:
                        srg_id = info["srg_id"]
                        if srg_id not in node.srg:
                            node.srg.create(srg_id)
                        tp.srg_id = srg_id

                    if info["direction"]:
                        tp.direction = info["direction"]

                    if info["frequency"]:
                        tp.frequency = info["frequency"]

                # ---------------------------
                #  DISCOVER EXISTING CONNECTIONS
                # ---------------------------
                try:
                    rc_list = dev.config.org_openroadm_device__org_openroadm_device.roadm_connections
                except Exception:
                    rc_list = []

                for rc in rc_list:
                    cname = str(rc.connection_name)
                    c = topo.connection.create(cname)
                    c.name = cname
                    c.device = dev_name
                    c.src_if = str(rc.source.src_if)
                    c.dst_if = str(rc.destination.dst_if)

            # Apply operational data update
            t.apply()

        output.result = "Discovery complete"


# ----------------------------------------------------------------------
# Action: BuildConnection
#   - DEG ↔ DEG  (using src-degree, dst-degree)
#   - DEG ↔ SRG1-PP (using src-degree, dst-pp)
# ----------------------------------------------------------------------
class BuildConnection(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output):
        log = ncs_log.Log("optical-build")

        device_name = str(input.device)
        freq_str = str(input.frequency)

        # We support:
        #  - src-degree (RX side)
        #  - dst-degree (TX side)
        #  - dst-pp (TX on SRG1-PPxx)
        src_deg = getattr(input, "src_degree", None)
        dst_deg = getattr(input, "dst_degree", None)
        dst_pp = getattr(input, "dst_pp", None)

        # Basic sanity
        if src_deg is None:
            output.result = "Error: src-degree must be provided"
            return

        if dst_deg is None and dst_pp is None:
            output.result = "Error: either dst-degree or dst-pp must be provided"
            return
        if dst_deg is not None and dst_pp is not None:
            output.result = "Error: provide only one of dst-degree or dst-pp"
            return

        # Convert numeric leaves (they may be maagic types)
        src_deg = int(src_deg)
        if dst_deg is not None:
            dst_deg = int(dst_deg)
        if dst_pp is not None:
            dst_pp = int(dst_pp)

        # Frequency overlap checks on DEG-side MC
        try:
            with ncs.maapi.single_read_trans(uinfo.username,
                                             uinfo.context,
                                             db=ncs.RUNNING) as rt:
                root_r = ncs.maagic.get_root(rt)
                dev_r = root_r.ncs__devices.device[device_name]

                # SRC DEG RX check
                if _slot_overlaps(dev_r, src_deg, "RX", freq_str):
                    output.result = (
                        f"Rejected: frequency slot {freq_str} overlaps existing "
                        f"MC on DEG{src_deg} RX"
                    )
                    return

                # DST DEG TX check (if DEG destination)
                if dst_deg is not None:
                    if _slot_overlaps(dev_r, dst_deg, "TX", freq_str):
                        output.result = (
                            f"Rejected: frequency slot {freq_str} overlaps existing "
                            f"MC on DEG{dst_deg} TX"
                        )
                        return
        except Exception as e:
            # If something goes wrong here, log and let device enforce constraints
            log.error(f"Overlap check error: {e}")

        with ncs.maapi.single_write_trans(uinfo.username,
                                          uinfo.context,
                                          db=ncs.RUNNING) as t:
            root = ncs.maagic.get_root(t)
            dev = root.ncs__devices.device[device_name]
            cfg = dev.config.org_openroadm_device__org_openroadm_device

            # --- Build endpoints ---

            # Source is always DEG (RX) for now
            ensure_mc_deg(dev, src_deg, "RX", freq_str)
            src_if_name = ensure_nmc_deg(dev, src_deg, "RX", freq_str)

            # Destination: either DEG (TX) or SRG1-PPxx (TX)
            if dst_deg is not None:
                ensure_mc_deg(dev, dst_deg, "TX", freq_str)
                dst_if_name = ensure_nmc_deg(dev, dst_deg, "TX", freq_str)
            else:
                # SRG1-PPxx TX
                dst_if_name = ensure_nmc_srg_pp(dev, dst_pp, "TX", freq_str)

            # --- Connection name ---
            if dst_deg is not None:
                conn_name = f"DEG{src_deg}-RX-to-DEG{dst_deg}-TX-{freq_str}"
            else:
                conn_name = f"DEG{src_deg}-RX-to-SRG1-PP{dst_pp:02d}-TX-{freq_str}"

            rc_list = cfg.roadm_connections
            if conn_name in rc_list:
                conn = rc_list[conn_name]
            else:
                conn = rc_list.create(conn_name)

            conn.source.src_if = src_if_name
            conn.destination.dst_if = dst_if_name
            conn.opticalControlMode = "off"
            if hasattr(conn, "target_output_power"):
                conn.target_output_power = 0.0

            t.apply()

        output.result = f"Connection {conn_name} created on {device_name}"


# ----------------------------------------------------------------------
# Action: DeleteConnection (smart cleanup of MC/NMC)
# ----------------------------------------------------------------------
class DeleteConnection(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output):
        log = ncs_log.Log("optical-delete")

        device_name = str(input.device)
        conn_name = str(input.connection_name)

        with ncs.maapi.single_write_trans(uinfo.username,
                                          uinfo.context,
                                          db=ncs.RUNNING) as t:
            root = ncs.maagic.get_root(t)
            dev = root.ncs__devices.device[device_name]
            cfg = dev.config.org_openroadm_device__org_openroadm_device

            if conn_name not in cfg.roadm_connections:
                output.result = (
                    f"Connection '{conn_name}' not found on device {device_name}"
                )
                return

            conn = cfg.roadm_connections[conn_name]
            src_if = str(conn.source.src_if)
            dst_if = str(conn.destination.dst_if)

            # Remove the ROADM connection itself
            del cfg.roadm_connections[conn_name]

            # Build a set of interfaces still used by any *other* roadm-connection
            used_if = set()
            for rc in cfg.roadm_connections:
                used_if.add(str(rc.source.src_if))
                used_if.add(str(rc.destination.dst_if))

            # Also protect MCs referenced via supporting-interface-list
            for if_name in list(used_if):
                if if_name in cfg.interface:
                    try:
                        sil = cfg.interface[if_name].supporting_interface_list
                        for s in sil:
                            used_if.add(str(s))
                    except Exception:
                        pass

            # Candidates to delete: src_if, dst_if, and their supporting interfaces
            delete_candidates = set([src_if, dst_if])

            for ep_if in [src_if, dst_if]:
                if ep_if in cfg.interface:
                    try:
                        sil = cfg.interface[ep_if].supporting_interface_list
                        for s in sil:
                            delete_candidates.add(str(s))
                    except Exception:
                        # No supporting-interface-list, ignore
                        pass

            # Now delete anything not used elsewhere
            for if_name in delete_candidates:
                if if_name in used_if:
                    continue
                if if_name in cfg.interface:
                    del cfg.interface[if_name]

            t.apply()

        output.result = (
            f"Connection '{conn_name}' and associated MC/NMC interfaces "
            f"successfully deleted on device {device_name}"
        )
