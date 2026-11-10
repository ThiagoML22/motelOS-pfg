-- Verifica la migracion 012 con el rol de la aplicacion, motel_app: un sello continua la cadena de su establecimiento,
-- no se edita ni se borra, y cada establecimiento ve solo los suyos. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_sellos.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    otro integer;
    conserje integer;
    guardia_uno integer;
    guardia_dos integer;
    arqueo_uno integer;
    arqueo_dos integer;
    sello bigint;
    cero char(64) := repeat('0', 64);
    primera char(64) := repeat('a', 64);
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-sel', 'Otro') RETURNING id INTO otro;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.s', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    ALTER TABLE arqueos_caja DISABLE TRIGGER USER;
    ALTER TABLE guardias DISABLE TRIGGER USER;
    INSERT INTO guardias (operador_id, franja, estado, cerrada_en) VALUES (conserje, '06:00', 'Cerrada', now())
    RETURNING id INTO guardia_uno;
    INSERT INTO guardias (operador_id, franja, estado, cerrada_en) VALUES (conserje, '14:00', 'Cerrada', now())
    RETURNING id INTO guardia_dos;
    INSERT INTO arqueos_caja (guardia_id, operador_id, confirmado_por_id, declarado_efectivo, total_declarado, diferencia, categoria)
    VALUES (guardia_uno, conserje, conserje, 0, 0, 0, 'Correcto') RETURNING id INTO arqueo_uno;
    INSERT INTO arqueos_caja (guardia_id, operador_id, confirmado_por_id, declarado_efectivo, total_declarado, diferencia, categoria)
    VALUES (guardia_dos, conserje, conserje, 0, 0, 0, 'Correcto') RETURNING id INTO arqueo_dos;
    ALTER TABLE arqueos_caja ENABLE TRIGGER USER;
    ALTER TABLE guardias ENABLE TRIGGER USER;

    SET LOCAL ROLE motel_app;

    -- 1. La cadena empieza en 1 y con la huella cero.
    bloqueado := false;
    BEGIN INSERT INTO sellos_arqueo (arqueo_id, secuencia, huella_anterior, huella) VALUES (arqueo_uno, 2, cero, primera);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se salteo un eslabon de la cadena'; END IF;
    INSERT INTO sellos_arqueo (arqueo_id, secuencia, huella_anterior, huella) VALUES (arqueo_uno, 1, cero, primera)
    RETURNING id INTO sello;

    -- 2. El siguiente sello tiene que apuntar a la huella anterior real.
    bloqueado := false;
    BEGIN INSERT INTO sellos_arqueo (arqueo_id, secuencia, huella_anterior, huella)
          VALUES (arqueo_dos, 2, repeat('b', 64), repeat('c', 64));
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se acepto un sello que no continua la cadena'; END IF;
    INSERT INTO sellos_arqueo (arqueo_id, secuencia, huella_anterior, huella)
    VALUES (arqueo_dos, 2, primera, repeat('c', 64));

    -- 3. Un sello no se edita ni se borra.
    bloqueado := false;
    BEGIN UPDATE sellos_arqueo SET huella = repeat('d', 64) WHERE id = sello;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se edito un sello'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM sellos_arqueo WHERE id = sello;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un sello'; END IF;

    -- 4. Otro establecimiento no ve los sellos del 1.
    PERFORM set_config('app.establecimiento_id', otro::text, true);
    SELECT count(*) INTO filas FROM sellos_arqueo;
    IF filas <> 0 THEN RAISE EXCEPTION 'Un establecimiento vio los sellos de otro'; END IF;
    RAISE NOTICE 'verify_sellos: cadena continua, solo agregado y aislamiento verificados';
END $$;
ROLLBACK;
