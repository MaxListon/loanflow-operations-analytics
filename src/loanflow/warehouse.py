"""Keep every analytical connection on the declared UTC reporting calendar."""
import duckdb


def connect_warehouse(path,read_only=False):
    con=duckdb.connect(str(path),read_only=read_only)
    con.execute("SET TimeZone='UTC'")
    return con
