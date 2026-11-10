-- db/migraciones/009_personalizacion_y_novedades.sql
-- Demostracion del Sprint 4 (copia local, no entregada): apariencia y avisos de cada establecimiento, y novedades
-- que se dejan entre guardias. Se aplica con el usuario dueno de las tablas, despues de 008_categorias_y_perfil.sql.

-- ---------------------------------------------------------------------------------------------------
-- Apariencia y avisos (RF-11): color de marca (el acento de la interfaz), eslogan que se ve al ingresar, minutos de
-- anticipacion del aviso "por vencer" de la grilla y alertas sonoras de la ventanilla. Los cambia la gerencia del
-- propio establecimiento (la politica cambio_propio_o_plataforma de la migracion 006 ya lo limita).
-- ---------------------------------------------------------------------------------------------------
ALTER TABLE establecimientos
    ADD COLUMN color_marca VARCHAR(7) CHECK (color_marca ~ '^#[0-9a-fA-F]{6}$'),
    ADD COLUMN eslogan VARCHAR(120),
    ADD COLUMN aviso_por_vencer_min INTEGER NOT NULL DEFAULT 10 CHECK (aviso_por_vencer_min BETWEEN 0 AND 120),
    ADD COLUMN alertas_sonoras BOOLEAN NOT NULL DEFAULT FALSE;

GRANT UPDATE (color_marca, eslogan, aviso_por_vencer_min, alertas_sonoras) ON establecimientos TO motel_app;
-- El alta de un motel por la plataforma (migracion 006) inserta todas las columnas del modelo, tambien estas.
GRANT INSERT (color_marca, eslogan, aviso_por_vencer_min, alertas_sonoras) ON establecimientos TO motel_app;

-- ---------------------------------------------------------------------------------------------------
-- Novedades de guardia: lo que el personal deja escrito para el turno siguiente y para la gerencia ("la 7 tiene la
-- ducha floja", "faltan toallas"). Solo se agregan; no se editan ni se borran. Cada una queda a nombre del usuario
-- de la sesion (app.operador_id, migracion 008) y, si la escribe un conserje, en su guardia abierta.
-- ---------------------------------------------------------------------------------------------------
CREATE TABLE novedades (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    operador_id INTEGER NOT NULL,
    guardia_id INTEGER,
    habitacion_id INTEGER,
    texto VARCHAR(500) NOT NULL CHECK (length(btrim(texto)) > 0),
    importante BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT novedades_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id),
    CONSTRAINT novedades_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id),
    CONSTRAINT novedades_habitacion_mismo_est FOREIGN KEY (establecimiento_id, habitacion_id)
        REFERENCES habitaciones (establecimiento_id, id)
);

CREATE INDEX novedades_recientes ON novedades (establecimiento_id, creado_en DESC);

-- La aplicacion no puede escribir a nombre de otro usuario ni en una guardia ajena o cerrada.
CREATE OR REPLACE FUNCTION check_novedad()
RETURNS TRIGGER AS $$
DECLARE
    g RECORD;
BEGIN
    IF current_user = 'motel_app' AND NEW.operador_id IS DISTINCT FROM app_operador() THEN
        RAISE EXCEPTION 'Novedades: se escriben solo a nombre del usuario de la sesion.';
    END IF;
    IF NEW.guardia_id IS NOT NULL THEN
        SELECT estado, operador_id INTO g FROM guardias WHERE id = NEW.guardia_id;
        IF g.estado IS DISTINCT FROM 'Abierta' OR g.operador_id IS DISTINCT FROM NEW.operador_id THEN
            RAISE EXCEPTION 'Novedades: la guardia % no es la guardia abierta de quien escribe.', NEW.guardia_id;
        END IF;
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_novedad
BEFORE INSERT ON novedades
FOR EACH ROW
EXECUTE FUNCTION check_novedad();

ALTER TABLE novedades ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON novedades TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

-- Solo agregado: sin UPDATE ni DELETE para la aplicacion.
GRANT SELECT, INSERT ON novedades TO motel_app;
GRANT USAGE ON SEQUENCE novedades_id_seq TO motel_app;
