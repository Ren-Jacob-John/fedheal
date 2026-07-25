"""
Reference implementation of a REAL (networked) Flower server — this is what
Module 3 graduates to once hospitals are actual separate machines instead of
one simulate.py process. Not used by simulate.py; kept here so the jump from
"simulation on my laptop" to "real server + real hospital clients" is a
small, obvious step rather than a rewrite.

Run the server:  python server.py
Run a client (from a "hospital" machine, once client_runner.py exists):
    python client_runner.py --hospital-id hospital-0 --server localhost:8080

This is next-sprint work — included now so Module 1's aggregation-server
plans (FastAPI + PostgreSQL for metadata, gRPC over TLS for transport) have
a concrete Flower piece to slot in next to.
"""
import flwr as fl

from model import build_model, get_model_parameters


def main():
    initial_parameters = fl.common.ndarrays_to_parameters(get_model_parameters(build_model()))

    strategy = fl.server.strategy.FedAvg(
        fraction_fit=1.0,           # use all connected hospitals every round
        fraction_evaluate=1.0,
        min_fit_clients=2,          # don't average with fewer than 2 hospitals
        min_available_clients=2,
        initial_parameters=initial_parameters,
    )

    fl.server.start_server(
        server_address="0.0.0.0:8080",
        config=fl.server.ServerConfig(num_rounds=8),
        strategy=strategy,
    )


if __name__ == "__main__":
    main()
