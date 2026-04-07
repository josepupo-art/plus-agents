import pandas as pd
from sheets_client import add_lead

FILE = "LEADS_actualizado.xlsx"


def import_leads():

    df = pd.read_excel(FILE)

    for _, row in df.iterrows():

        nombre = str(row.get("Nombre", ""))
        telefono = str(row.get("Telefono normalizado", ""))

        if telefono and telefono != "nan":

            print("Importando:", nombre, telefono)

            add_lead(nombre, telefono, "odontologo", "excel")


if __name__ == "__main__":

    import_leads()