-- Verifica la migracion 013 con el rol de la aplicacion, motel_app: un pedido del cliente solo entra en un turno en curso,
-- no se borra, lo pedido no cambia, se atiende una sola vez a nombre del usuario de la sesion y cada establecimiento ve
-- solo los suyos. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_pedidos_cliente.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    conserje integer;
    ajeno integer;
    categoria integer;
    tarifa integer;
    habitacion integer;
    habitacion_dos integer;
    guardia integer;
    turno uuid;
    turno_cerrado uuid;
    articulo integer;
    pedido integer;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-cli', 'Otro') RETURNING id INTO otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.c', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.c2', 'Otro', 'x', 'OPERADOR')
    RETURNING id INTO ajeno;
    INSERT INTO categorias_habitacion (nombre) VALUES ('Verif cliente') RETURNING id INTO categoria;
    INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente, categoria_id)
    VALUES ('Verif cliente', 8000, 120, 0, 30, 2500, true, categoria) RETURNING id INTO tarifa;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9921, 'Ocupada', categoria) RETURNING id INTO habitacion;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9922, 'Libre', categoria) RETURNING id INTO habitacion_dos;
    INSERT INTO guardias (operador_id, franja) VALUES (conserje, '06:00') RETURNING id INTO guardia;
    INSERT INTO articulos (codigo, descripcion, precio_unitario, stock_actual) VALUES ('VERIF-C', 'Agua', 800, 3)
    RETURNING id INTO articulo;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (gen_random_uuid(), habitacion, tarifa, 'Auto', now(), 'En Curso', 8000, 8000, conserje, guardia)
    RETURNING id INTO turno;
    ALTER TABLE turnos DISABLE TRIGGER USER;
    INSERT INTO turnos (id, habitacion_id, tarifa_id, tipo_cliente, hora_inicio, hora_fin, estado, tarifa_base, total_general,
                        operador_apertura_id, guardia_apertura_id, operador_cierre_id)
    VALUES (gen_random_uuid(), habitacion_dos, tarifa, 'Auto', now(), now(), 'FINALIZADO', 8000, 8000, conserje, guardia, conserje)
    RETURNING id INTO turno_cerrado;
    ALTER TABLE turnos ENABLE TRIGGER USER;
    PERFORM set_config('app.operador_id', conserje::text, true);

    SET LOCAL ROLE motel_app;

    -- 1. Un turno en curso recibe pedidos; uno cerrado, no.
    INSERT INTO pedidos_cliente (turno_id, tipo, articulo_id, cantidad) VALUES (turno, 'ARTICULO', articulo, 2)
    RETURNING id INTO pedido;
    bloqueado := false;
    BEGIN INSERT INTO pedidos_cliente (turno_id, tipo) VALUES (turno_cerrado, 'TOALLAS');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un pedido en un turno cerrado'; END IF;

    -- 2. Sin texto libre: un tipo desconocido, cantidades fuera de rango o un articulo sin cantidad no entran.
    bloqueado := false;
    BEGIN INSERT INTO pedidos_cliente (turno_id, tipo) VALUES (turno, 'OTRO');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un pedido de tipo desconocido'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO pedidos_cliente (turno_id, tipo, articulo_id, cantidad) VALUES (turno, 'ARTICULO', articulo, 99);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro una cantidad fuera de rango'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO pedidos_cliente (turno_id, tipo, articulo_id) VALUES (turno, 'ARTICULO', articulo);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un articulo sin cantidad'; END IF;

    -- 3. Nadie lo atiende a nombre de otro, y lo pedido no cambia.
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET estado = 'Atendido', atendido_por_id = ajeno, atendido_en = now() WHERE id = pedido;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se atendio un pedido a nombre de otro'; END IF;
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET cantidad = 5 WHERE id = pedido;
    EXCEPTION WHEN insufficient_privilege OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se cambio lo pedido'; END IF;

    -- 4. Se atiende una vez y no se borra.
    UPDATE pedidos_cliente SET estado = 'Atendido', atendido_por_id = conserje, atendido_en = now() WHERE id = pedido;
    bloqueado := false;
    BEGIN UPDATE pedidos_cliente SET estado = 'Rechazado' WHERE id = pedido;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se atendio dos veces un pedido'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM pedidos_cliente WHERE id = pedido;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un pedido'; END IF;

    -- 5. Otro establecimiento no ve los pedidos del 1.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT count(*) INTO filas FROM pedidos_cliente;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio los pedidos de otro'; END IF;
    RAISE NOTICE 'verify_pedidos_cliente: turno en curso, sin texto libre, atencion unica y aislamiento verificados';
END $$;
ROLLBACK;
