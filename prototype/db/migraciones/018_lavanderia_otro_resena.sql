-- db/migraciones/018_lavanderia_otro_resena.sql
-- Demostracion del Sprint 4 (copia local, no entregada): lavanderia propia, motivo «Otro» y resena corta del cliente.
-- Se aplica con el usuario dueno de las tablas, despues de 017_recuento_de_ropa.sql.
--
-- 1. La mayoria de los moteles lava su propia ropa: entonces la ropa nunca sale del motel y el conserje solo anota lo que
--    se compra y lo que se tira. Si la lavanderia es de afuera, ademas anota lo que sale y lo que vuelve. Lo decide la
--    gerencia; lo ya anotado no cambia.
-- 2. «Se fue un cliente» suma el motivo «Otro», con unas palabras que lo explican (nada de la persona).
-- 3. La calificacion del cliente puede llevar una resena de hasta seis palabras. El filtro de palabras groseras esta en
--    la aplicacion; la base asegura el largo.

-- 1. Lavanderia propia o de afuera.
ALTER TABLE establecimientos ADD COLUMN lavanderia_propia BOOLEAN NOT NULL DEFAULT true;
GRANT INSERT (lavanderia_propia) ON establecimientos TO motel_app;
GRANT UPDATE (lavanderia_propia) ON establecimientos TO motel_app;

-- Con lavanderia propia no hay ropa que salga o vuelva de una lavanderia de afuera.
CREATE OR REPLACE FUNCTION check_ropa_movimiento_lavanderia()
RETURNS TRIGGER AS $$
DECLARE
    propia BOOLEAN;
BEGIN
    IF current_user = 'motel_app' AND NEW.tipo IN ('LAVANDERIA_SALE', 'LAVANDERIA_VUELVE') THEN
        SELECT lavanderia_propia INTO propia FROM establecimientos WHERE id = NEW.establecimiento_id;
        IF propia THEN
            RAISE EXCEPTION 'Ropa: este establecimiento lava su ropa; no hay envios a una lavanderia de afuera.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_ropa_movimiento_lavanderia
BEFORE INSERT ON ropa_movimientos
FOR EACH ROW
EXECUTE FUNCTION check_ropa_movimiento_lavanderia();

-- 2. El motivo «Otro» y su detalle: solo con «Otro», y con «Otro» es obligatorio.
ALTER TABLE clientes_perdidos DROP CONSTRAINT clientes_perdidos_motivo_check;
ALTER TABLE clientes_perdidos ADD CONSTRAINT clientes_perdidos_motivo_check
    CHECK (motivo IN ('SIN_LUGAR', 'ESPERA', 'PRECIO', 'OTRO'));
ALTER TABLE clientes_perdidos ADD COLUMN detalle VARCHAR(80);
ALTER TABLE clientes_perdidos ADD CONSTRAINT clientes_perdidos_detalle_otro CHECK (
    (motivo = 'OTRO') = (detalle IS NOT NULL)
    AND (detalle IS NULL OR length(btrim(detalle)) > 0)
);

-- 3. La resena: hasta 60 letras y seis palabras, en una sola linea.
ALTER TABLE calificaciones ADD COLUMN resena VARCHAR(60);
ALTER TABLE calificaciones ADD CONSTRAINT calificaciones_resena_corta CHECK (
    resena IS NULL
    OR (
        length(btrim(resena)) > 0
        AND resena !~ '[\r\n\t]'
        AND array_length(regexp_split_to_array(btrim(resena), '\s+'), 1) <= 6
    )
);
