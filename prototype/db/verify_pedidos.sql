-- Verifica la migracion 010 con el rol de la aplicacion, motel_app: los pedidos de reposicion no se borran, lo pedido
-- no cambia, lo recibido se anota una sola vez mientras el pedido esta pendiente, un pedido cerrado no cambia mas y
-- cada establecimiento ve solo los suyos. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_pedidos.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    gerencia_id integer;
    articulo integer;
    pedido integer;
    item integer;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-ped', 'Otro') RETURNING id INTO otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.p', 'Gerencia', 'x', 'ADMINISTRADOR')
    RETURNING id INTO gerencia_id;
    INSERT INTO articulos (codigo, descripcion, precio_unitario, stock_actual) VALUES ('VERIF-P', 'Agua', 800, 3)
    RETURNING id INTO articulo;

    SET LOCAL ROLE motel_app;

    -- 1. Alta del pedido con su articulo.
    INSERT INTO pedidos_reposicion (creado_por_id, proveedor) VALUES (gerencia_id, 'Proveedor') RETURNING id INTO pedido;
    INSERT INTO pedido_items (pedido_id, articulo_id, cantidad) VALUES (pedido, articulo, 24) RETURNING id INTO item;

    -- 2. No se borra ni cambia lo pedido.
    bloqueado := false;
    BEGIN DELETE FROM pedidos_reposicion WHERE id = pedido;
    EXCEPTION WHEN insufficient_privilege OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un pedido'; END IF;
    bloqueado := false;
    BEGIN UPDATE pedido_items SET cantidad = 1 WHERE id = item;
    EXCEPTION WHEN insufficient_privilege OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio lo pedido'; END IF;
    bloqueado := false;
    BEGIN UPDATE pedidos_reposicion SET estado = 'Recibido' WHERE id = pedido;
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cerro un pedido sin quien lo cerro'; END IF;

    -- 3. Recepcion: lo recibido una vez, y despues el pedido cerrado no cambia.
    UPDATE pedido_items SET recibida = 20 WHERE id = item;
    bloqueado := false;
    BEGIN UPDATE pedido_items SET recibida = 24 WHERE id = item;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio lo recibido'; END IF;
    UPDATE pedidos_reposicion SET estado = 'Recibido', cerrado_por_id = gerencia_id, cerrado_en = now() WHERE id = pedido;
    bloqueado := false;
    BEGIN UPDATE pedidos_reposicion SET estado = 'Anulado' WHERE id = pedido;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se reabrio un pedido cerrado'; END IF;

    -- 4. Otro establecimiento no ve los pedidos del 1.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT count(*) INTO filas FROM pedidos_reposicion;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio los pedidos de otro'; END IF;
    SELECT count(*) INTO filas FROM pedido_items;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio los articulos pedidos por otro'; END IF;
    RAISE NOTICE 'verify_pedidos: pedidos de solo agregado, recepcion unica y aislamiento verificados';
END $$;
ROLLBACK;
