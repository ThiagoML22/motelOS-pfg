-- db/migraciones/003_cierre_supervisado.sql
-- Cierre supervisado de una guardia abandonada: si el conserje se va sin hacer su arqueo, la gerencia cuenta
-- la gaveta y confirma el arqueo en su lugar, tambien a ciegas (RN-RES-03). El arqueo sigue siendo de la
-- caja del conserje (operador_id) y registra quien lo confirmo y por que.
-- Se aplica con el usuario dueno de las tablas, despues de 002_v2_caja.sql.

ALTER TABLE arqueos_caja
    ADD COLUMN confirmado_por_id INTEGER REFERENCES operadores(id),
    ADD COLUMN observacion VARCHAR(300);

-- Todo arqueo nuevo dice quien lo confirmo; uno confirmado por otra persona exige una observacion.
ALTER TABLE arqueos_caja ADD CONSTRAINT arqueo_confirmado_por
    CHECK (confirmado_por_id IS NOT NULL) NOT VALID;
ALTER TABLE arqueos_caja ADD CONSTRAINT arqueo_supervisado_con_observacion
    CHECK (confirmado_por_id = operador_id OR length(trim(coalesce(observacion, ''))) >= 10) NOT VALID;

-- El arqueo lo confirma el operador de la guardia o, en un cierre supervisado, un ADMINISTRADOR.
CREATE OR REPLACE FUNCTION calcular_arqueo()
RETURNS TRIGGER AS $$
DECLARE
    g RECORD;
    rol_confirma VARCHAR(20);
BEGIN
    SELECT estado, operador_id, fondo_inicial INTO g FROM guardias WHERE id = NEW.guardia_id FOR UPDATE;
    IF g.estado IS DISTINCT FROM 'Abierta' THEN
        RAISE EXCEPTION 'RN-RES-02: La guardia % ya esta cerrada.', NEW.guardia_id;
    END IF;
    IF NEW.operador_id IS DISTINCT FROM g.operador_id THEN
        RAISE EXCEPTION 'RNF-04: El arqueo pertenece a la caja del operador de la guardia.';
    END IF;
    IF NEW.confirmado_por_id IS NULL THEN
        NEW.confirmado_por_id := NEW.operador_id;
    END IF;
    IF NEW.confirmado_por_id <> g.operador_id THEN
        SELECT rol INTO rol_confirma FROM operadores WHERE id = NEW.confirmado_por_id;
        IF rol_confirma IS DISTINCT FROM 'ADMINISTRADOR' THEN
            RAISE EXCEPTION 'RNF-04: Solo el operador de la guardia o la gerencia confirman su arqueo.';
        END IF;
    END IF;

    SELECT g.fondo_inicial + COALESCE(SUM(monto) FILTER (WHERE medio_pago = 'EFECTIVO'), 0),
           COALESCE(SUM(monto) FILTER (WHERE medio_pago = 'POSNET'), 0),
           COALESCE(SUM(monto) FILTER (WHERE medio_pago = 'MERCADO_PAGO'), 0)
      INTO NEW.sistema_efectivo, NEW.sistema_posnet, NEW.sistema_mercado_pago
      FROM pagos WHERE guardia_id = NEW.guardia_id;

    NEW.total_declarado := NEW.declarado_efectivo + NEW.declarado_posnet + NEW.declarado_mercado_pago;
    NEW.total_sistema := NEW.sistema_efectivo + NEW.sistema_posnet + NEW.sistema_mercado_pago;
    NEW.diferencia := NEW.total_declarado - NEW.total_sistema;
    NEW.categoria := CASE WHEN NEW.diferencia = 0 THEN 'Correcto'
                          WHEN NEW.diferencia < 0 THEN 'Faltante'
                          ELSE 'Sobrante' END;
    NEW.confirmado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
