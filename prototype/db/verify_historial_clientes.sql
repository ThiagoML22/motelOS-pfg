-- Verifica la migracion 011 con el rol de la aplicacion, motel_app: el historial de estados y los clientes perdidos son
-- de solo agregado, quedan a nombre del usuario de la sesion y con la hora de la base, un cliente perdido va en la
-- guardia abierta de quien lo registra y cada establecimiento ve solo lo suyo. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_historial_clientes.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    conserje integer;
    ajeno integer;
    categoria integer;
    habitacion integer;
    guardia integer;
    evento bigint;
    perdido integer;
    momento timestamptz;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-his', 'Otro') RETURNING id INTO otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.h', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.h2', 'Otro', 'x', 'OPERADOR')
    RETURNING id INTO ajeno;
    INSERT INTO categorias_habitacion (nombre) VALUES ('Verif historial') RETURNING id INTO categoria;
    INSERT INTO habitaciones (numero, estado, categoria_id) VALUES (9911, 'Libre', categoria) RETURNING id INTO habitacion;
    INSERT INTO guardias (operador_id, franja) VALUES (conserje, '06:00') RETURNING id INTO guardia;
    PERFORM set_config('app.operador_id', conserje::text, true);

    SET LOCAL ROLE motel_app;

    -- 1. Un evento se escribe con la hora de la base, aunque la aplicacion mande otra.
    INSERT INTO eventos_habitacion (habitacion_id, estado_anterior, estado_nuevo, origen, operador_id, creado_en)
    VALUES (habitacion, 'Libre', 'Mantenimiento', 'MANUAL', conserje, TIMESTAMPTZ '2020-01-01')
    RETURNING id, creado_en INTO evento, momento;
    IF momento < now() - INTERVAL '1 hour' THEN RAISE EXCEPTION 'Un evento quedo con la hora que mando la aplicacion'; END IF;

    -- 2. Nadie escribe a nombre de otro.
    bloqueado := false;
    BEGIN INSERT INTO eventos_habitacion (habitacion_id, estado_anterior, estado_nuevo, origen, operador_id)
          VALUES (habitacion, 'Libre', 'Mantenimiento', 'MANUAL', ajeno);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se escribio un evento a nombre de otro usuario'; END IF;

    -- 3. El evento tiene que cambiar el estado y usar un origen conocido.
    bloqueado := false;
    BEGIN INSERT INTO eventos_habitacion (habitacion_id, estado_anterior, estado_nuevo, origen, operador_id)
          VALUES (habitacion, 'Libre', 'Libre', 'MANUAL', conserje);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se registro un evento sin cambio de estado'; END IF;

    -- 4. El historial no se edita ni se borra.
    bloqueado := false;
    BEGIN UPDATE eventos_habitacion SET estado_nuevo = 'Libre' WHERE id = evento;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se edito el historial'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM eventos_habitacion WHERE id = evento;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro el historial'; END IF;

    -- 5. Un cliente perdido va en la guardia abierta de quien lo registra y tampoco se borra.
    INSERT INTO clientes_perdidos (motivo, operador_id, guardia_id) VALUES ('SIN_LUGAR', conserje, guardia)
    RETURNING id INTO perdido;
    bloqueado := false;
    BEGIN INSERT INTO clientes_perdidos (motivo, operador_id, guardia_id) VALUES ('SIN_LUGAR', ajeno, guardia);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se registro un cliente a nombre de otro usuario'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO clientes_perdidos (motivo, operador_id, guardia_id) VALUES ('ROBO', conserje, guardia);
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se acepto un motivo desconocido'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM clientes_perdidos WHERE id = perdido;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un cliente perdido'; END IF;

    -- 6. En una guardia cerrada ya no se registra.
    RESET ROLE;
    ALTER TABLE guardias DISABLE TRIGGER USER;
    UPDATE guardias SET estado = 'Cerrada', cerrada_en = now() WHERE id = guardia;
    ALTER TABLE guardias ENABLE TRIGGER USER;
    SET LOCAL ROLE motel_app;
    bloqueado := false;
    BEGIN INSERT INTO clientes_perdidos (motivo, operador_id, guardia_id) VALUES ('ESPERA', conserje, guardia);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se registro un cliente en una guardia cerrada'; END IF;

    -- 7. Otro establecimiento no ve nada del 1.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT count(*) INTO filas FROM eventos_habitacion;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio el historial de otro'; END IF;
    SELECT count(*) INTO filas FROM clientes_perdidos;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio los clientes perdidos de otro'; END IF;
    RAISE NOTICE 'verify_historial_clientes: solo agregado, autoria, guardia abierta y aislamiento verificados';
END $$;
ROLLBACK;
