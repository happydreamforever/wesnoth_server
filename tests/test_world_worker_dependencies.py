"""Package provenance and isolated prefix preservation; no simulated native build."""
from contextlib import redirect_stdout
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import world_worker_dependencies as deps
from tools import build_world_worker as build

class DependencyPrefix(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='worker deps ');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.msys=self.root/'msys';self.prefix=self.root/'isolated'
        self.local=self.msys/'var/lib/pacman/local';self.local.mkdir(parents=True)
        self.package('tool',{'bin/g++.exe':b'verified tool'},depends=['mingw-w64-x86_64-runtime'])
        self.package('runtime',{'bin/runtime.dll':b'verified dll','share/empty':b''})
        self.required=['bin/g++.exe']
    def package(self,name,files,depends=()):
        directory=self.local/('mingw-w64-x86_64-'+name+'-1-1');directory.mkdir()
        full='mingw-w64-x86_64-'+name
        (directory/'desc').write_text('%NAME%\n'+full+'\n\n%VERSION%\n1-1\n\n%DEPENDS%\n'+'\n'.join(depends)+'\n')
        (directory/'files').write_text('%FILES%\n'+'\n'.join('mingw64/'+p for p in files)+'\n')
        mtree=['#mtree','/set type=file uid=0 gid=0 mode=644']
        for name,raw in files.items():
            path=self.msys/'mingw64'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            mtree.append('./mingw64/'+name+' size='+str(len(raw))+' sha256digest='+hashlib.sha256(raw).hexdigest())
        (directory/'mtree').write_bytes(gzip.compress('\n'.join(mtree).encode()))
    def prepare(self):
        with redirect_stdout(io.StringIO()):return deps.prepare(self.msys,self.required,self.prefix)
    def test_exact_package_closure_zero_files_and_reuse(self):
        self.package('unrelated',{'share/unrelated':b'do not copy'})
        source={p.relative_to(self.msys).as_posix():p.read_bytes() for p in self.msys.rglob('*') if p.is_file()}
        self.assertEqual(self.prepare(),self.prefix)
        receipt=deps.verify(self.prefix)
        self.assertEqual(len(receipt['packages']),2);self.assertEqual(len(receipt['files']),3)
        self.assertFalse((self.prefix/'share/unrelated').exists())
        self.assertEqual(self.prepare(),self.prefix)
        self.assertEqual(source,{p.relative_to(self.msys).as_posix():p.read_bytes() for p in self.msys.rglob('*') if p.is_file()})
    def test_installed_file_tampering_never_prepares_prefix(self):
        (self.msys/'mingw64/bin/runtime.dll').write_bytes(b'changed DLL')
        with self.assertRaisesRegex(deps.BuildError,'integrity record'):self.prepare()
        self.assertFalse(self.prefix.exists())
    def test_missing_dependency_and_missing_package_metadata_refuse(self):
        (self.local/'mingw-w64-x86_64-runtime-1-1/desc').write_text('%NAME%\nmingw-w64-x86_64-other\n%VERSION%\n1\n')
        with self.assertRaisesRegex(deps.BuildError,'missing or ambiguous'):self.prepare()
    def test_version_constraints_use_readonly_resolver_and_fail_closed(self):
        records=[{'depends':['mingw-w64-x86_64-runtime>=1:2.3-4']}]
        with patch.object(deps.subprocess,'run') as run:
            run.return_value.returncode=127
            with self.assertRaisesRegex(deps.BuildError,'versions do not satisfy'):
                deps.verify_dependency_versions(self.msys,records)
            self.assertEqual(run.call_args.args[0][1:],['--deptest','--','mingw-w64-x86_64-runtime>=1:2.3-4'])
            run.return_value.returncode=0
            deps.verify_dependency_versions(self.msys,records)
    def test_isolated_tamper_extra_file_and_receipt_duplicates_reject(self):
        self.prepare();receipt=(self.prefix/'receipt.json').read_bytes()
        (self.prefix/'unexpected.dll').write_bytes(b'not approved')
        with self.assertRaisesRegex(deps.BuildError,'unrecorded'):deps.verify(self.prefix)
        (self.prefix/'unexpected.dll').unlink();(self.prefix/'bin/runtime.dll').write_bytes(b'changed')
        with self.assertRaisesRegex(deps.BuildError,'changed'):deps.verify(self.prefix)
        (self.prefix/'receipt.json').write_bytes(b'{"format":1,"format":1}')
        with self.assertRaisesRegex(deps.BuildError,'Duplicate'):deps.verify(self.prefix)
    def test_symlinked_dependency_and_foreign_prefix_are_preserved(self):
        dll=self.msys/'mingw64/bin/runtime.dll';dll.unlink();dll.symlink_to(self.msys/'mingw64/bin/g++.exe')
        with self.assertRaisesRegex(deps.BuildError,'links'):self.prepare()
        dll.unlink();dll.write_bytes(b'verified dll');self.prefix.mkdir();(self.prefix/'foreign.txt').write_text('keep')
        with self.assertRaises((deps.BuildError,FileNotFoundError)):self.prepare()
        self.assertEqual((self.prefix/'foreign.txt').read_text(),'keep')
    def test_readonly_audit_can_create_new_report_and_marks_missing(self):
        report=self.root/'audit.json'
        with redirect_stdout(io.StringIO()):result=build.dependency_audit(self.msys,report)
        self.assertFalse(result['complete']);self.assertFalse(result['runtime_tested'])
        self.assertTrue(report.is_file());self.assertFalse(self.prefix.exists())

    def test_runtime_dll_inventory_rejects_extra_or_changed_library(self):
        pin=patch.object(build,'verify_pinned_data');pin.start();self.addCleanup(pin.stop)
        stage=self.root/'worker';binary=stage/'bin';binary.mkdir(parents=True)
        executable=binary/'world-worker.exe';executable.write_bytes(b'fixture executable')
        library=binary/'runtime.dll';library.write_bytes(b'fixture private library')
        data=self.root/'game data';(data/'data').mkdir(parents=True);(data/'data/_main.cfg').write_text('fixture')
        expected={'purpose':'fixture binding'}
        receipt={'binding':expected,'executable':{'bytes':executable.stat().st_size,'sha256':deps.digest(executable)},
            'dlls':{'private':{'runtime.dll':{'filename':'runtime.dll','bytes':library.stat().st_size,'sha256':deps.digest(library)}},'windows_system':['kernel32.dll']},
            'version':'fixture 1.19.26','game_data':str(data),'game_data_files':build.data_inventory(data),
            'build_tools':{name:{'path':str(executable),'sha256':deps.digest(executable),'version':'fixture'} for name in ('cmake','ninja')}}
        (stage/'receipt.json').write_text(json.dumps(receipt))
        with patch.object(build,'STAGE',stage):
            self.assertEqual(build.installed_worker(expected_binding=expected)['executable'],executable)
            extra=binary/'unexpected.dll';extra.write_bytes(b'unrecorded')
            with self.assertRaisesRegex(deps.BuildError,'unrecorded'):build.installed_worker(expected_binding=expected)
            extra.unlink();library.write_bytes(b'changed')
            with self.assertRaisesRegex(deps.BuildError,'private DLL differs'):build.installed_worker(expected_binding=expected)

    def test_native_cmake_uses_pinned_flattened_lua_and_plain_link_signature(self):
        source=build.CLIENT/'engine/CMakeLists.txt';before=source.read_bytes()
        text=build.worker_cmake(build.CLIENT,self.root/'generated',[])
        self.assertIn('src/modules/lua/lapi.c',text)
        self.assertIn('filesystem graph container)',text)
        self.assertIn('target_link_libraries(wesnoth OpenSSL::SSL',text)
        self.assertNotIn('target_link_libraries(wesnoth PRIVATE',text)
        self.assertEqual(source.read_bytes(),before)

    def test_interrupted_source_copy_must_match_derived_inputs(self):
        client=self.root/'client';engine=client/'engine';(engine/'src').mkdir(parents=True)
        (engine/'src/keep.cpp').write_bytes(b'original');(engine/'src/change.cpp').write_bytes(b'old')
        (engine/'CMakeLists.txt').write_bytes(b'old configuration')
        generated=self.root/'generated';generated.mkdir();(generated/'change.cpp').write_bytes(b'owned replacement')
        source=self.root/'source';mapping={'change.cpp':'src/change.cpp'}
        expected=build.prepare_source(client,source,generated,mapping,'derived configuration\n')
        self.assertEqual(build.prepare_source(client,source,generated,mapping,'derived configuration\n'),expected)
        altered=source/'src/keep.cpp';altered.write_bytes(b'changed during interrupted build')
        with self.assertRaisesRegex(deps.BuildError,'source copy is incomplete or changed'):
            build.prepare_source(client,source,generated,mapping,'derived configuration\n')
        self.assertEqual(altered.read_bytes(),b'changed during interrupted build')
        self.assertEqual((engine/'src/keep.cpp').read_bytes(),b'original')

    def test_first_build_rejects_unpinned_data_even_with_main_config(self):
        data=self.root/'modified data';(data/'data').mkdir(parents=True)
        (data/'data/_main.cfg').write_text('untrusted first-build game data')
        with self.assertRaisesRegex(deps.BuildError,'differs from the pinned'):
            build.data_inventory(data)

    def test_worker_rejects_changed_original_engine_manifest(self):
        client=self.root/'changed client';(client/'engine').mkdir(parents=True);(client/'tools').mkdir()
        (client/'tools/prepare_android_source.py').write_bytes((build.CLIENT/'tools/prepare_android_source.py').read_bytes())
        (client/'engine/source-manifest.json').write_text('{}')
        with patch.object(build,'CLIENT',client),self.assertRaisesRegex(deps.BuildError,'manifest differs'):
            build.verify_engine()
        self.assertEqual((client/'engine/source-manifest.json').read_text(),'{}')

    def test_worker_build_requires_pinned_archive_prefix_before_native_tools(self):
        from tools import world_worker_archive_prefix as archive
        with patch.object(build,'STAGE',self.root/'isolated-worker'), \
                patch.object(build,'check_host'), patch.object(archive,'verify_locked_prefix',
                side_effect=deps.BuildError('unapproved dependency prefix')) as verify, \
                patch.object(build,'data_inventory') as data:
            with self.assertRaisesRegex(deps.BuildError,'unapproved dependency prefix'):
                build.build(self.msys,self.root/'cmake',self.root/'data',False)
            verify.assert_called_once_with()
            data.assert_not_called()

    def test_prefix_preparation_verifies_offline_cache_before_extraction(self):
        from tools import world_worker_archive_prefix as archive
        from tools import world_worker_packages as packages
        calls=[]
        with patch.object(build,'check_host'), \
                patch.object(build.sys,'argv',['build_world_worker.py','--msys',str(self.msys),'--prepare-dependencies']), \
                patch.object(packages,'execute',side_effect=lambda *a,**k:calls.append(('cache',a,k))), \
                patch.object(archive,'prepare_archive_prefix',side_effect=lambda *a,**k:calls.append(('prefix',a,k))):
            self.assertEqual(build.main(),0)
        self.assertEqual([row[0] for row in calls],['cache','prefix'])
        self.assertEqual(calls[0][2],{'download':False})
        self.assertEqual(calls[1][2]['msys'], self.msys)
        with patch.object(build,'check_host'), \
                patch.object(build.sys,'argv',['build_world_worker.py','--msys',str(self.msys),'--prepare-dependencies']), \
                patch.object(packages,'execute',side_effect=deps.BuildError('signature rejected')), \
                patch.object(archive,'prepare_archive_prefix') as prepare, redirect_stdout(io.StringIO()):
            self.assertEqual(build.main(),1)
            prepare.assert_not_called()

if __name__=='__main__':unittest.main()
