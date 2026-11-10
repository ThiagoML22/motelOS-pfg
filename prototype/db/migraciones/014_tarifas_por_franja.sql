-- db/migraciones/014_tarifas_por_franja.sql
-- Demostracion del Sprint 4 (copia local, no entregada): tarifas especiales por dia y franja horaria.
-- Se aplica con el usuario dueno de las tablas, despues de 013_pedidos_del_cliente.sql.
--
-- Una categoria sigue teniendo su tarifa general y puede sumar franjas: «viernes y sabado de 20 a 6». La franja dice
-- cuando rige; su precio es una fila de tarifas como cualquier otra, que tampoco se edita: se reemplaza (RN-DER-06). Asi
-- la liquidacion no cambia: el turno guarda tarifa_id al abrirse y conserva esa tarifa hasta el cobro.
--
-- Los dias de una franja son los de COMIENZO: la noche del viernes sigue rigiendo el sabado a las 2. Dos franjas activas
-- de una categoria no pueden pisarse: a cada minuto de la semana le corresponde una sola tarifa, y eso lo garantiza la
-- base con una restriccion de exclusion, tambien frente a dos cambios simultaneos.

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Los minutos de la semana que cubre una franja (lunes 00:00 = 0). desde = hasta es el dia completo; hasta <= desde
-- cruza la medianoche, y lo que pasa del domingo vuelve al lunes.
CREATE OR REPLACE FUNCTION franja_en_la_semana(p_dias SMALLINT, p_desde TIME, p_hasta TIME)
RETURNS int4multirange AS $$
DECLARE
    semana CONSTANT INTEGER := 10080;
    inicio INTEGER := EXTRACT(HOUR FROM p_desde)::INTEGER * 60 + EXTRACT(MINUTE FROM p_desde)::INTEGER;
    fin INTEGER := EXTRACT(HOUR FROM p_hasta)::INTEGER * 60 + EXTRACT(MINUTE FROM p_hasta)::INTEGER;
    resultado int4multirange := '{}';
    a INTEGER;
    b INTEGER;
BEGIN
    IF fin <= inicio THEN
        fin := fin + 1440;
    END IF;
    FOR dia IN 0..6 LOOP
        IF (p_dias::INTEGER & (1 << dia)) <> 0 THEN
            a := dia * 1440 + inicio;
            b := dia * 1440 + fin;
            IF b <= semana THEN
                resultado := resultado + int4multirange(int4range(a, b));
            ELSE
                resultado := resultado + int4multirange(int4range(a, semana)) + int4multirange(int4range(0, b - semana));
            END IF;
        END IF;
    END LOOP;
    RETURN resultado;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE TABLE franjas_tarifa (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    categoria_id INTEGER NOT NULL,
    nombre VARCHAR(40) NOT NULL,
    -- Mascara de dias de comienzo: lunes = 1, martes = 2, ... domingo = 64.
    dias SMALLINT NOT NULL CHECK (dias BETWEEN 1 AND 127),
    desde TIME NOT NULL,
    hasta TIME NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    creada_por_id INTEGER,
    creada_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    semana int4multirange GENERATED ALWAYS AS (franja_en_la_semana(dias, desde, hasta)) STORED,
    CONSTRAINT franjas_tarifa_est_id UNIQUE (establecimiento_id, id),
    CONSTRAINT franjas_tarifa_est_cat_id UNIQUE (establecimiento_id, categoria_id, id),
    CONSTRAINT franjas_tarifa_categoria_mismo_est FOREIGN KEY (establecimiento_id, categoria_id)
        REFERENCES categorias_habitacion (establecimiento_id, id),
    CONSTRAINT franjas_tarifa_creada_por_mismo_est FOREIGN KEY (establecimiento_id, creada_por_id)
        REFERENCES operadores (establecimiento_id, id),
    CONSTRAINT franjas_tarifa_sin_superposicion
        EXCLUDE USING gist (establecimiento_id WITH =, categoria_id WITH =, semana WITH &&) WHERE (activa)
);

CREATE UNIQUE INDEX franjas_tarifa_nombre ON franjas_tarifa (establecimiento_id, categoria_id, lower(nombre))
    WHERE activa;

-- La tarifa de una franja es de la misma categoria que la franja.
ALTER TABLE tarifas ADD COLUMN franja_id INTEGER;
ALTER TABLE tarifas ADD CONSTRAINT tarifas_franja_misma_categoria
    FOREIGN KEY (establecimiento_id, categoria_id, franja_id)
    REFERENCES franjas_tarifa (establecimiento_id, categoria_id, id);

-- Una sola tarifa general vigente por categoria y una sola vigente por franja.
DROP INDEX tarifas_una_vigente;
CREATE UNIQUE INDEX tarifas_una_vigente ON tarifas (establecimiento_id, categoria_id)
    WHERE vigente AND franja_id IS NULL;
CREATE UNIQUE INDEX tarifas_una_vigente_por_franja ON tarifas (establecimiento_id, franja_id)
    WHERE vigente AND franja_id IS NOT NULL;

ALTER TABLE franjas_tarifa ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON franjas_tarifa TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

-- Una franja se da de baja, no se borra: los turnos que la usaron siguen apuntando a su tarifa.
GRANT SELECT, INSERT ON franjas_tarifa TO motel_app;
GRANT UPDATE (nombre, dias, desde, hasta, activa) ON franjas_tarifa TO motel_app;
GRANT USAGE ON SEQUENCE franjas_tarifa_id_seq TO motel_app;
GRANT INSERT (franja_id) ON tarifas TO motel_app;
