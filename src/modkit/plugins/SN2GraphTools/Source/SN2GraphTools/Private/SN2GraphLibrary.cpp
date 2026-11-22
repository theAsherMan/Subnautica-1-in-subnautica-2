#include "SN2GraphLibrary.h"

#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "Engine/Blueprint.h"
#include "K2Node_CallArrayFunction.h"
#include "K2Node_CallFunction.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_Event.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_MacroInstance.h"
#include "K2Node_Self.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Modules/ModuleManager.h"
#include "UObject/UnrealType.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, SN2GraphTools);

DEFINE_LOG_CATEGORY_STATIC(LogSN2Graph, Log, All);

namespace
{
	template <typename T>
	T* Place(UEdGraph* Graph, int32 X, int32 Y, TFunctionRef<void(T*)> Setup)
	{
		if (!Graph)
		{
			return nullptr;
		}
		Graph->Modify();
		FGraphNodeCreator<T> Creator(*Graph);
		T* Node = Creator.CreateNode(false);
		Setup(Node);
		Node->NodePosX = X;
		Node->NodePosY = Y;
		Creator.Finalize();
		return Node;
	}

	UEdGraphPin* FindPinLoose(UEdGraphNode* Node, const FString& Name)
	{
		if (!Node)
		{
			return nullptr;
		}
		if (UEdGraphPin* P = Node->FindPin(FName(*Name)))
		{
			return P;
		}
		for (UEdGraphPin* P : Node->Pins)
		{
			if (P && (P->PinName.ToString().Equals(Name, ESearchCase::IgnoreCase) || P->GetDisplayName().ToString().Equals(Name, ESearchCase::IgnoreCase)))
			{
				return P;
			}
		}
		return nullptr;
	}

	UBlueprint* BlueprintOf(UEdGraph* Graph)
	{
		return Graph ? FBlueprintEditorUtils::FindBlueprintForGraph(Graph) : nullptr;
	}
}

UEdGraph* USN2GraphLibrary::GetEventGraph(UBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		return nullptr;
	}
	if (UEdGraph* G = FBlueprintEditorUtils::FindEventGraph(Blueprint))
	{
		return G;
	}
	UEdGraph* G = FBlueprintEditorUtils::CreateNewGraph(Blueprint, UEdGraphSchema_K2::GN_EventGraph, UEdGraph::StaticClass(), UEdGraphSchema_K2::StaticClass());
	FBlueprintEditorUtils::AddUbergraphPage(Blueprint, G);
	return G;
}

int32 USN2GraphLibrary::ClearGraph(UEdGraph* Graph)
{
	UBlueprint* BP = BlueprintOf(Graph);
	if (!Graph || !BP)
	{
		return 0;
	}
	TArray<UEdGraphNode*> Nodes = Graph->Nodes;
	for (UEdGraphNode* N : Nodes)
	{
		if (N)
		{
			FBlueprintEditorUtils::RemoveNode(BP, N, true);
		}
	}
	return Nodes.Num();
}

UEdGraphNode* USN2GraphLibrary::AddEventOverride(UBlueprint* Blueprint, UEdGraph* Graph, FName EventName, int32 X, int32 Y)
{
	if (!Blueprint || !Blueprint->ParentClass)
	{
		return nullptr;
	}
	UFunction* Fn = Blueprint->ParentClass->FindFunctionByName(EventName);
	if (!Fn)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("AddEventOverride: %s not found on %s"), *EventName.ToString(), *Blueprint->ParentClass->GetName());
		return nullptr;
	}
	UClass* Owner = Fn->GetOwnerClass();
	return Place<UK2Node_Event>(Graph, X, Y, [&](UK2Node_Event* N)
	{
		N->EventReference.SetExternalMember(EventName, Owner);
		N->bOverrideFunction = true;
	});
}

UEdGraphNode* USN2GraphLibrary::AddCustomEvent(UEdGraph* Graph, FName EventName, int32 X, int32 Y)
{
	return Place<UK2Node_CustomEvent>(Graph, X, Y, [&](UK2Node_CustomEvent* N)
	{
		N->CustomFunctionName = EventName;
	});
}

UEdGraphNode* USN2GraphLibrary::AddCallFunction(UEdGraph* Graph, UClass* FunctionOwner, FName FunctionName, int32 X, int32 Y)
{
	UFunction* Fn = FunctionOwner ? FunctionOwner->FindFunctionByName(FunctionName) : nullptr;
	if (!Fn)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("AddCallFunction: %s not found on %s"), *FunctionName.ToString(), FunctionOwner ? *FunctionOwner->GetName() : TEXT("null"));
		return nullptr;
	}
	// KismetArrayLibrary functions use wildcard array pins and need the array-aware node class.
	if (Fn->GetOwnerClass() && Fn->GetOwnerClass()->GetFName() == FName(TEXT("KismetArrayLibrary")))
	{
		return Place<UK2Node_CallArrayFunction>(Graph, X, Y, [&](UK2Node_CallArrayFunction* N)
		{
			N->SetFromFunction(Fn);
		});
	}
	return Place<UK2Node_CallFunction>(Graph, X, Y, [&](UK2Node_CallFunction* N)
	{
		N->SetFromFunction(Fn);
	});
}

UEdGraphNode* USN2GraphLibrary::AddStandardMacro(UEdGraph* Graph, FName MacroName, int32 X, int32 Y)
{
	UBlueprint* Macros = LoadObject<UBlueprint>(nullptr, TEXT("/Engine/EditorBlueprintResources/StandardMacros.StandardMacros"));
	if (!Macros)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("StandardMacros not found"));
		return nullptr;
	}
	UEdGraph* Macro = nullptr;
	for (UEdGraph* G : Macros->MacroGraphs)
	{
		if (G && G->GetFName() == MacroName)
		{
			Macro = G;
			break;
		}
	}
	if (!Macro)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("macro %s not found"), *MacroName.ToString());
		return nullptr;
	}
	return Place<UK2Node_MacroInstance>(Graph, X, Y, [&](UK2Node_MacroInstance* N)
	{
		N->SetMacroGraph(Macro);
	});
}

UEdGraphNode* USN2GraphLibrary::AddBranch(UEdGraph* Graph, int32 X, int32 Y)
{
	return Place<UK2Node_IfThenElse>(Graph, X, Y, [](UK2Node_IfThenElse*) {});
}

UEdGraphNode* USN2GraphLibrary::AddSequence(UEdGraph* Graph, int32 NumOutputs, int32 X, int32 Y)
{
	UK2Node_ExecutionSequence* N = Place<UK2Node_ExecutionSequence>(Graph, X, Y, [](UK2Node_ExecutionSequence*) {});
	if (N)
	{
		int32 Outputs = 0;
		for (UEdGraphPin* P : N->Pins)
		{
			if (P && P->Direction == EGPD_Output)
			{
				++Outputs;
			}
		}
		for (; Outputs < NumOutputs; ++Outputs)
		{
			N->AddInputPin();
		}
	}
	return N;
}

UEdGraphNode* USN2GraphLibrary::AddSelf(UEdGraph* Graph, int32 X, int32 Y)
{
	return Place<UK2Node_Self>(Graph, X, Y, [](UK2Node_Self*) {});
}

bool USN2GraphLibrary::AddMemberVariable(UBlueprint* Blueprint, FName Name, FName PinCategory, FName PinSubCategory, UObject* SubCategoryObject, bool bIsArray, const FString& DefaultValue)
{
	if (!Blueprint)
	{
		return false;
	}
	if (FBlueprintEditorUtils::FindNewVariableIndex(Blueprint, Name) != INDEX_NONE)
	{
		FBlueprintEditorUtils::RemoveMemberVariable(Blueprint, Name);
	}
	FEdGraphPinType Type;
	Type.PinCategory = PinCategory;
	Type.PinSubCategory = PinSubCategory;
	Type.PinSubCategoryObject = SubCategoryObject;
	Type.ContainerType = bIsArray ? EPinContainerType::Array : EPinContainerType::None;
	return FBlueprintEditorUtils::AddMemberVariable(Blueprint, Name, Type, DefaultValue);
}

UEdGraphNode* USN2GraphLibrary::AddVariableNode(UBlueprint* Blueprint, UEdGraph* Graph, FName Name, bool bSetter, int32 X, int32 Y)
{
	if (bSetter)
	{
		return Place<UK2Node_VariableSet>(Graph, X, Y, [&](UK2Node_VariableSet* N)
		{
			N->VariableReference.SetSelfMember(Name);
		});
	}
	return Place<UK2Node_VariableGet>(Graph, X, Y, [&](UK2Node_VariableGet* N)
	{
		N->VariableReference.SetSelfMember(Name);
	});
}

bool USN2GraphLibrary::SetPinDefault(UEdGraphNode* Node, const FString& PinName, const FString& Value)
{
	UEdGraphPin* Pin = FindPinLoose(Node, PinName);
	if (!Pin)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("SetPinDefault: no pin %s on %s"), *PinName, Node ? *Node->GetName() : TEXT("null"));
		return false;
	}
	GetDefault<UEdGraphSchema_K2>()->TrySetDefaultValue(*Pin, Value);
	return true;
}

bool USN2GraphLibrary::SetPinDefaultObject(UEdGraphNode* Node, const FString& PinName, UObject* Object)
{
	UEdGraphPin* Pin = FindPinLoose(Node, PinName);
	if (!Pin)
	{
		UE_LOG(LogSN2Graph, Warning, TEXT("SetPinDefaultObject: no pin %s on %s"), *PinName, Node ? *Node->GetName() : TEXT("null"));
		return false;
	}
	GetDefault<UEdGraphSchema_K2>()->TrySetDefaultObject(*Pin, Object);
	return true;
}

bool USN2GraphLibrary::Connect(UEdGraphNode* From, const FString& FromPin, UEdGraphNode* To, const FString& ToPin, FString& OutMessage)
{
	UEdGraphPin* A = FindPinLoose(From, FromPin);
	UEdGraphPin* B = FindPinLoose(To, ToPin);
	if (!A || !B)
	{
		OutMessage = FString::Printf(TEXT("pin not found: %s.%s=%s, %s.%s=%s"),
			From ? *From->GetName() : TEXT("null"), *FromPin, A ? TEXT("ok") : TEXT("MISSING"),
			To ? *To->GetName() : TEXT("null"), *ToPin, B ? TEXT("ok") : TEXT("MISSING"));
		return false;
	}
	const UEdGraphSchema_K2* K2 = GetDefault<UEdGraphSchema_K2>();
	const FPinConnectionResponse R = K2->CanCreateConnection(A, B);
	OutMessage = R.Message.ToString();
	if (R.Response == CONNECT_RESPONSE_DISALLOW)
	{
		return false;
	}
	return K2->TryCreateConnection(A, B);
}

TArray<FString> USN2GraphLibrary::DescribePins(UEdGraphNode* Node)
{
	TArray<FString> Out;
	if (!Node)
	{
		return Out;
	}
	for (UEdGraphPin* P : Node->Pins)
	{
		if (!P)
		{
			continue;
		}
		Out.Add(FString::Printf(TEXT("%s %s : %s/%s(%s)%s [%s]"),
			P->Direction == EGPD_Input ? TEXT("in ") : TEXT("out"),
			*P->PinName.ToString(),
			*P->PinType.PinCategory.ToString(),
			*P->PinType.PinSubCategory.ToString(),
			P->PinType.PinSubCategoryObject.IsValid() ? *P->PinType.PinSubCategoryObject->GetName() : TEXT(""),
			P->PinType.IsArray() ? TEXT("[]") : TEXT(""),
			*P->GetDefaultAsString()));
	}
	return Out;
}

bool USN2GraphLibrary::CompileWithLog(UBlueprint* Blueprint, TArray<FString>& OutMessages)
{
	if (!Blueprint)
	{
		return false;
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	FCompilerResultsLog Log;
	Log.bSilentMode = true;
	FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::None, &Log);
	for (const TSharedRef<FTokenizedMessage>& M : Log.Messages)
	{
		OutMessages.Add(M->ToText().ToString());
	}
	return Blueprint->Status != BS_Error;
}

namespace
{
	FArrayProperty* FindObjectArrayProperty(UObject* Object, FName PropertyName)
	{
		if (!Object)
		{
			return nullptr;
		}
		FArrayProperty* Arr = CastField<FArrayProperty>(FindFProperty<FProperty>(Object->GetClass(), PropertyName));
		if (!Arr || !CastField<FObjectPropertyBase>(Arr->Inner))
		{
			return nullptr;
		}
		return Arr;
	}
}

TArray<FString> USN2GraphLibrary::DescribeObjectArray(UObject* Object, FName PropertyName)
{
	TArray<FString> Out;
	FArrayProperty* Arr = FindObjectArrayProperty(Object, PropertyName);
	if (!Arr)
	{
		Out.Add(FString::Printf(TEXT("MISSING %s"), *PropertyName.ToString()));
		return Out;
	}
	FObjectPropertyBase* Inner = CastField<FObjectPropertyBase>(Arr->Inner);
	FScriptArrayHelper Helper(Arr, Arr->ContainerPtrToValuePtr<void>(Object));
	for (int32 i = 0; i < Helper.Num(); ++i)
	{
		UObject* E = Inner->GetObjectPropertyValue(Helper.GetRawPtr(i));
		Out.Add(FString::Printf(TEXT("%d %s outer=%s"), i,
			E ? *E->GetPathName() : TEXT("None"),
			(E && E->GetOuter()) ? *E->GetOuter()->GetPathName() : TEXT("None")));
	}
	return Out;
}

int32 USN2GraphLibrary::ClearObjectArray(UObject* Object, FName PropertyName)
{
	FArrayProperty* Arr = FindObjectArrayProperty(Object, PropertyName);
	if (!Arr)
	{
		return -1;
	}
	Object->Modify();
	FScriptArrayHelper Helper(Arr, Arr->ContainerPtrToValuePtr<void>(Object));
	const int32 N = Helper.Num();
	Helper.EmptyValues();
	return N;
}

void USN2GraphLibrary::NotifyPropertyChanged(UObject* Object, FName PropertyName)
{
	if (!Object)
	{
		return;
	}
	FProperty* Prop = FindFProperty<FProperty>(Object->GetClass(), PropertyName);
	if (!Prop)
	{
		return;
	}
	Object->PreEditChange(Prop);
	FPropertyChangedEvent Ev(Prop, EPropertyChangeType::ValueSet);
	Object->PostEditChangeProperty(Ev);
}
