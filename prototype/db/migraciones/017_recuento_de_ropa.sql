-- db/migraciones/017_recuento_de_ropa.sql
-- Demostracion del Sprint 4 (copia local, no entregada): cada establecimiento elige como cuenta su ropa.
-- Se aplica con el usuario dueno de las tablas, despues de 016_operacion_diaria.sql.
--
-- Hay moteles que cuentan las toallas y las sabanas separadas en limpias, sucias y en uso, y otros que las cuentan todas
-- juntas. Lo decide la gerencia. Lo que se compara entre un recuento y el siguiente es siempre el total, asi que cambiar
-- la forma de contar no corta el historial.

ALTER TABLE establecimientos ADD COLUMN ropa_por_estado BOOLEAN NOT NULL DEFAULT true;
GRANT INSERT (ropa_por_estado) ON establecimientos TO motel_app;
GRANT UPDATE (ropa_por_estado) ON establecimientos TO motel_app;

-- El total pasa a guardarse: en un recuento «todo junto» es el unico dato.
ALTER TABLE ropa_conteos ADD COLUMN total INTEGER;
UPDATE ropa_conteos SET total = limpias + sucias + en_habitaciones;
ALTER TABLE ropa_conteos ALTER COLUMN total SET NOT NULL;
ALTER TABLE ropa_conteos ALTER COLUMN limpias DROP NOT NULL;
ALTER TABLE ropa_conteos ALTER COLUMN sucias DROP NOT NULL;
ALTER TABLE ropa_conteos ALTER COLUMN en_habitaciones DROP NOT NULL;
ALTER TABLE ropa_conteos ADD CONSTRAINT ropa_conteos_total_coherente CHECK (
    total BETWEEN 0 AND 300000
    AND (
        (limpias IS NULL AND sucias IS NULL AND en_habitaciones IS NULL)
        OR (limpias IS NOT NULL AND sucias IS NOT NULL AND en_habitaciones IS NOT NULL
            AND total = limpias + sucias + en_habitaciones)
    )
);

-- El recuento va como lo pide su establecimiento: separado o todo junto, sin mezclas. Si viene separado y sin total, el
-- total es la suma.
CREATE OR REPLACE FUNCTION check_ropa_conteo_forma()
RETURNS TRIGGER AS $$
DECLARE
    separado BOOLEAN;
BEGIN
    IF NEW.total IS NULL AND NEW.limpias IS NOT NULL AND NEW.sucias IS NOT NULL AND NEW.en_habitaciones IS NOT NULL THEN
        NEW.total := NEW.limpias + NEW.sucias + NEW.en_habitaciones;
    END IF;
    SELECT ropa_por_estado INTO separado FROM establecimientos WHERE id = NEW.establecimiento_id;
    IF current_user = 'motel_app' AND separado IS DISTINCT FROM (NEW.limpias IS NOT NULL) THEN
        RAISE EXCEPTION 'Ropa: este establecimiento cuenta %.',
            CASE WHEN separado THEN 'por separado: limpias, sucias y en uso' ELSE 'todo junto' END;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_ropa_conteo_forma
BEFORE INSERT ON ropa_conteos
FOR EACH ROW
EXECUTE FUNCTION check_ropa_conteo_forma();
