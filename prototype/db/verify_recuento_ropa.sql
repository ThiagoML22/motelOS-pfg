-- Verifica la migracion 017 con el rol de la aplicacion, motel_app: el recuento va como lo pide el establecimiento (separado
-- o todo junto), el total siempre es coherente y la gerencia puede cambiar la forma de contar sin tocar lo ya contado.
-- Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_recuento_ropa.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    conserje integer;
    guardia integer;
    suma integer;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.r', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    INSERT INTO guardias (operador_id, franja) VALUES (conserje, '06:00') RETURNING id INTO guardia;
    UPDATE establecimientos SET ropa_por_estado = true WHERE id = 1;
    PERFORM set_config('app.operador_id', conserje::text, true);

    SET LOCAL ROLE motel_app;

    -- 1. Separado: el total es la suma, aunque no se mande.
    INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, limpias, sucias, en_habitaciones)
    VALUES (guardia, conserje, 'APERTURA', 'TOALLAS', 40, 10, 16) RETURNING total INTO suma;
    IF suma <> 66 THEN RAISE EXCEPTION 'El total no es la suma: %', suma; END IF;

    -- 2. Un total que no coincide con sus partes no entra.
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, limpias, sucias, en_habitaciones, total)
    VALUES (guardia, conserje, 'APERTURA', 'SABANAS', 30, 6, 16, 60);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un total distinto de la suma'; END IF;

    -- 3. Ni un recuento a medias.
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, limpias, total)
    VALUES (guardia, conserje, 'APERTURA', 'SABANAS', 30, 30);
    EXCEPTION WHEN check_violation OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un recuento a medias'; END IF;

    -- 4. Donde se cuenta separado, no entra un recuento todo junto.
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, total)
    VALUES (guardia, conserje, 'APERTURA', 'SABANAS', 52);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un recuento todo junto donde se cuenta separado'; END IF;

    -- 5. La gerencia cambia la forma de contar: lo ya contado queda como estaba.
    UPDATE establecimientos SET ropa_por_estado = false WHERE id = 1;
    SELECT count(*) INTO filas FROM ropa_conteos WHERE guardia_id = guardia AND limpias = 40 AND total = 66;
    IF filas <> 1 THEN RAISE EXCEPTION 'Cambio un recuento anterior'; END IF;

    -- 6. Ahora entra todo junto, y no separado.
    INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, total)
    VALUES (guardia, conserje, 'APERTURA', 'SABANAS', 52);
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, limpias, sucias, en_habitaciones)
    VALUES (guardia, conserje, 'CIERRE', 'TOALLAS', 40, 10, 16);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un recuento separado donde se cuenta todo junto'; END IF;

    -- 7. Sin total no hay recuento, y no puede ser negativo.
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda) VALUES (guardia, conserje, 'CIERRE', 'TOALLAS');
    EXCEPTION WHEN not_null_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un recuento sin total'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO ropa_conteos (guardia_id, operador_id, momento, prenda, total) VALUES (guardia, conserje, 'CIERRE', 'TOALLAS', -1);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un total negativo'; END IF;

    RAISE NOTICE 'verify_recuento_ropa: forma del recuento por establecimiento, total coherente y cambio sin tocar el historial verificados';
END $$;
ROLLBACK;
