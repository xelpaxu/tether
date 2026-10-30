from app.models.network import Gateway
from app.network.platform import default_routes


def get_gateways(interface_name: str | None = None) -> list[Gateway]:
    gateways = [Gateway(ip=r['NextHop'], interface=r['InterfaceAlias'],
                        interface_index=r['InterfaceIndex'],
                        metric=int(r.get('RouteMetric') or 0) + int(r.get('InterfaceMetric') or 0))
                for r in default_routes() if not interface_name or r['InterfaceAlias'] == interface_name]
    return sorted(gateways, key=lambda g: g.metric)


async def check_gateway(gateway: Gateway) -> Gateway:
    from app.network.connectivity import ping
    result = await ping(gateway.ip)
    return gateway.model_copy(update={'reachability': result.reachability})
