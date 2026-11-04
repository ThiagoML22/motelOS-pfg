-- db/migraciones/012_sellos_de_arqueo.sql
-- Demostracion del Sprint 4 (copia local, no entregada): comprobantes verificables.
-- Se aplica con el usuario dueno de las tablas, despues de 011_historial_y_clientes_perdidos.sql.
--
-- Cada arqueo recibe una huella (SHA-256) calculada con sus datos, sus cobros y la huella del arqueo anterior: una
-- cadena por establecimiento. Si alguien cambia un importe directamente en la base, la huella deja de coincidir; si
-- ademas recalcula esa huella, se corta la cadena con el siguiente; y si rehace toda la cadena, ya no coincide con la
-- huella impresa en los comprobantes firmados. La huella la calcula la aplicacion; la base garantiza que la cadena no
-- se salte eslabones y que un sello no se edite ni se borre.

ALTER TABLE arqueos_caja ADD CONSTRAINT arqueos_est_id UNIQUE (establecimiento_id, id);

CREATE TABLE sellos_arqueo (
    id BIGSERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    arqueo_id INTEGER NOT NULL,
    secuencia INTEGER NOT NULL CHECK (secuencia > 0),
    huella_anterior CHAR(64) NOT NULL,
    huella CHAR(64) NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT sellos_un_sello_por_arqueo UNIQUE (arqueo_id),
    CONSTRAINT sellos_secuencia_por_establecimiento UNIQUE (establecimiento_id, secuencia),
    CONSTRAINT sellos_arqueo_mismo_est FOREIGN KEY (establecimiento_id, arqueo_id)
        REFERENCES arqueos_caja (establecimiento_id, id)
);

CREATE INDEX sellos_por_huella ON sellos_arqueo (establecimiento_id, huella);

-- El sello nuevo continua la cadena: la secuencia siguiente y la huella anterior del ultimo sello del establecimiento.
CREATE OR REPLACE FUNCTION check_sello_arqueo()
RETURNS TRIGGER AS $$
DECLARE
    ultima_secuencia INTEGER;
    ultima_huella CHAR(64);
BEGIN
    SELECT secuencia, huella INTO ultima_secuencia, ultima_huella
    FROM sellos_arqueo
    WHERE establecimiento_id = NEW.establecimiento_id
    ORDER BY secuencia DESC
    LIMIT 1;
    IF NEW.secuencia IS DISTINCT FROM COALESCE(ultima_secuencia, 0) + 1
       OR NEW.huella_anterior IS DISTINCT FROM COALESCE(ultima_huella, repeat('0', 64)) THEN
        RAISE EXCEPTION 'Sellos: el sello no continua la cadena del establecimiento.';
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_sello_arqueo
BEFORE INSERT ON sellos_arqueo
FOR EACH ROW
EXECUTE FUNCTION check_sello_arqueo();

ALTER TABLE sellos_arqueo ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON sellos_arqueo TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

-- Solo agregado: sin UPDATE ni DELETE para la aplicacion.
GRANT SELECT, INSERT ON sellos_arqueo TO motel_app;
GRANT USAGE ON SEQUENCE sellos_arqueo_id_seq TO motel_app;
